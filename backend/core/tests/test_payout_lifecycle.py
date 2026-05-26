"""Tests for the safe landlord-payout state machine.

Covers:
  - REQUESTED → PROCESSING on provider acceptance
  - REQUESTED → PAID on explicit settlement (rare)
  - REQUESTED → FAILED + funds restored on provider rejection
  - REQUESTED stays REQUESTED on transport_error without provider_reference
  - PROCESSING reconciliation (settled / rejected / still-processing)
  - Idempotency: same idempotency_key returns the existing payout
  - Admin mark-paid restricted to PROCESSING
  - Admin reverse restores funds
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import (
    LandlordBalance,
    LandlordPayout,
    LandlordSettings,
    LedgerTransaction,
    Profile,
)


STRONG_PASSWORD = "StrongPass1234!"


class _PayoutBase(APITestCase):
    def setUp(self):
        self.landlord = self._make_user("ll_lifecycle", Profile.ROLE_LANDLORD)
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Lifecycle LL",
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0712345678",
            },
        )
        # No recent destination change → cool-down doesn't apply.
        LandlordSettings.objects.filter(user=self.landlord).update(
            payout_destination_updated_at=None
        )
        self.balance = LandlordBalance.objects.create(
            landlord=self.landlord,
            available_balance=Decimal("20000.00"),
            locked_balance=Decimal("0.00"),
        )

    def _make_user(self, username, role, *, is_staff=False):
        user = User.objects.create_user(username=username, password=STRONG_PASSWORD)
        if is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        profile = user.profile
        profile.role = role
        profile.save(update_fields=["role"])
        return user

    def _auth(self, user):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"username": user.username, "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def _request_payout(self, amount="5000.00", idempotency_key=None, destination="0712345678"):
        body = {
            "amount": amount,
            "method": LandlordPayout.METHOD_MPESA,
            "destination": destination,
        }
        headers = {}
        if idempotency_key:
            headers["HTTP_X_IDEMPOTENCY_KEY"] = str(idempotency_key)
        return self.client.post(
            reverse("landlord-payout-request"), body, format="json", **headers
        )


# ---------------------------------------------------------------------------
# Provider acceptance → PROCESSING (NOT PAID)
# ---------------------------------------------------------------------------


class PayoutAcceptedTests(_PayoutBase):
    @patch("core.views.execute_intasend_payout")
    def test_accepted_outcome_marks_processing_not_paid(self, mock_exec):
        mock_exec.return_value = {
            "outcome": "accepted",
            "provider_reference": "track-1",
            "provider_status": "SENT",
            "detail": None,
            "redacted_response": {"status": "SENT", "tracking_id": "track-1"},
        }
        self._auth(self.landlord)
        response = self._request_payout()
        # 202 Accepted communicates "we have it, awaiting settlement".
        self.assertEqual(response.status_code, 202, response.data)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_PROCESSING)
        self.assertEqual(payout.provider_reference, "track-1")
        self.assertEqual(payout.provider_status, "SENT")
        self.assertIsNotNone(payout.processing_at)
        # Funds reserved, not yet paid out: available_balance dropped, no
        # PAID ledger row exists yet.
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_balance, Decimal("15000.00"))
        self.assertFalse(
            LedgerTransaction.objects.filter(
                user=self.landlord,
                kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
            ).exists()
        )


# ---------------------------------------------------------------------------
# Provider explicit "settled" → PAID immediately (only for instant rails)
# ---------------------------------------------------------------------------


class PayoutSettledImmediatelyTests(_PayoutBase):
    @patch("core.views.execute_intasend_payout")
    def test_settled_outcome_marks_paid_and_writes_ledger(self, mock_exec):
        mock_exec.return_value = {
            "outcome": "settled",
            "provider_reference": "settled-1",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {"status": "COMPLETED", "tracking_id": "settled-1"},
        }
        self._auth(self.landlord)
        response = self._request_payout()
        self.assertEqual(response.status_code, 201, response.data)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_PAID)
        self.assertIsNotNone(payout.paid_at)
        # Exactly one PAID ledger row exists.
        paid_rows = LedgerTransaction.objects.filter(
            user=self.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
        )
        self.assertEqual(paid_rows.count(), 1)


# ---------------------------------------------------------------------------
# Provider rejection → FAILED + funds restored
# ---------------------------------------------------------------------------


class PayoutRejectedTests(_PayoutBase):
    @patch("core.views.execute_intasend_payout")
    def test_rejected_outcome_restores_funds(self, mock_exec):
        mock_exec.return_value = {
            "outcome": "rejected",
            "provider_reference": None,
            "provider_status": "REJECTED",
            "detail": "Provider declined the transfer.",
            "redacted_response": {"status": "REJECTED"},
        }
        self._auth(self.landlord)
        response = self._request_payout()
        self.assertEqual(response.status_code, 502)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_FAILED)
        self.balance.refresh_from_db()
        # Reservation released — back to the original balance.
        self.assertEqual(self.balance.available_balance, Decimal("20000.00"))


# ---------------------------------------------------------------------------
# Ambiguous / transport_error → keep reservation (no auto-reverse)
# ---------------------------------------------------------------------------


class PayoutAmbiguousTests(_PayoutBase):
    @patch("core.views.execute_intasend_payout")
    def test_ambiguous_with_reference_moves_to_processing(self, mock_exec):
        mock_exec.return_value = {
            "outcome": "ambiguous",
            "provider_reference": "amb-ref-1",
            "provider_status": None,
            "detail": "weird-shaped response",
            "redacted_response": {"weird": True},
        }
        self._auth(self.landlord)
        response = self._request_payout()
        # 202 — caller knows it's pending verification.
        self.assertEqual(response.status_code, 202)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_PROCESSING)
        self.assertEqual(payout.provider_reference, "amb-ref-1")
        # Funds remain reserved — we have not auto-reversed.
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_balance, Decimal("15000.00"))

    @patch("core.views.execute_intasend_payout")
    def test_transport_error_without_reference_stays_requested(self, mock_exec):
        mock_exec.return_value = {
            "outcome": "transport_error",
            "provider_reference": None,
            "provider_status": None,
            "detail": "timeout",
            "redacted_response": {},
        }
        self._auth(self.landlord)
        response = self._request_payout()
        self.assertEqual(response.status_code, 202)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        # No provider_reference → we cannot upgrade to PROCESSING and we
        # must not auto-reverse either (the request may have actually reached
        # the provider). Reconciliation / admin retry will resolve it.
        self.assertEqual(payout.status, LandlordPayout.STATUS_REQUESTED)
        self.assertIsNone(payout.provider_reference)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_balance, Decimal("15000.00"))


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class PayoutIdempotencyTests(_PayoutBase):
    @patch("core.views.execute_intasend_payout")
    def test_same_idempotency_key_does_not_double_submit(self, mock_exec):
        mock_exec.return_value = {
            "outcome": "accepted",
            "provider_reference": "idem-1",
            "provider_status": "SENT",
            "detail": None,
            "redacted_response": {},
        }
        self._auth(self.landlord)
        key = uuid.uuid4()
        first = self._request_payout(idempotency_key=key)
        self.assertEqual(first.status_code, 202)
        first_id = first.data["payout"]["id"] if "payout" in first.data else first.data["id"]
        # Second request, same key — must NOT call the provider again, must
        # NOT debit again, and must return the existing payout row.
        second = self._request_payout(idempotency_key=key)
        self.assertIn(second.status_code, (200, 202))
        second_id = second.data["id"] if "id" in second.data else second.data["payout"]["id"]
        self.assertEqual(first_id, second_id)
        self.assertEqual(mock_exec.call_count, 1)
        self.balance.refresh_from_db()
        # Single deduction.
        self.assertEqual(self.balance.available_balance, Decimal("15000.00"))

    def test_invalid_idempotency_key_is_rejected(self):
        self._auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "1000.00",
                "method": LandlordPayout.METHOD_MPESA,
                "destination": "0712345678",
            },
            format="json",
            HTTP_X_IDEMPOTENCY_KEY="not-a-uuid",
        )
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class PayoutReconciliationTests(_PayoutBase):
    def _processing_payout(self, *, reference="track-recon", amount=Decimal("5000.00")):
        # Deduct so the balance reflects an in-flight reservation, then
        # write a PROCESSING row directly.
        self.balance.available_balance = self.balance.available_balance - amount
        self.balance.save(update_fields=["available_balance", "updated_at"])
        payout = LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=amount,
            method=LandlordPayout.METHOD_MPESA,
            destination="254712345678",
            status=LandlordPayout.STATUS_PROCESSING,
            requested_by=self.landlord,
            provider_reference=reference,
            processing_at=timezone.now(),
        )
        LedgerTransaction.objects.create(
            user=self.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
            amount=amount,
            status=LedgerTransaction.STATUS_PENDING,
            reference_text=f"payout:{payout.id}",
        )
        return payout

    @patch("core.services.intasend_payout_status")
    def test_settled_status_promotes_to_paid(self, mock_status):
        payout = self._processing_payout(reference="reco-paid")
        mock_status.return_value = {
            "outcome": "settled",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {"status": "COMPLETED"},
        }
        from core.services import reconcile_processing_payouts
        stats = reconcile_processing_payouts()
        self.assertEqual(stats["paid"], 1)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_PAID)
        self.assertEqual(
            LedgerTransaction.objects.filter(
                user=self.landlord,
                kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
                reference_text__contains=f"payout:{payout.id};source:reconcile",
            ).count(),
            1,
        )

    @patch("core.services.intasend_payout_status")
    def test_rejected_status_reverses_and_restores_funds(self, mock_status):
        payout = self._processing_payout(reference="reco-rev")
        mock_status.return_value = {
            "outcome": "rejected",
            "provider_status": "FAILED",
            "detail": None,
            "redacted_response": {"status": "FAILED"},
        }
        balance_before = LandlordBalance.objects.get(landlord=self.landlord).available_balance
        from core.services import reconcile_processing_payouts
        stats = reconcile_processing_payouts()
        self.assertEqual(stats["reversed"], 1)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_REVERSED)
        balance_after = LandlordBalance.objects.get(landlord=self.landlord).available_balance
        self.assertEqual(balance_after, balance_before + payout.amount)

    @patch("core.services.intasend_payout_status")
    def test_still_processing_is_left_alone(self, mock_status):
        payout = self._processing_payout(reference="reco-stay")
        mock_status.return_value = {
            "outcome": "accepted",
            "provider_status": "SENT",
            "detail": None,
            "redacted_response": {"status": "SENT"},
        }
        from core.services import reconcile_processing_payouts
        stats = reconcile_processing_payouts()
        self.assertEqual(stats["left_processing"], 1)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_PROCESSING)
        self.assertIsNotNone(payout.last_reconciled_at)

    @patch("core.services.intasend_payout_status")
    def test_management_command_runs(self, mock_status):
        self._processing_payout(reference="reco-cmd")
        mock_status.return_value = {
            "outcome": "settled",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {},
        }
        stdout = StringIO()
        call_command("reconcile_payouts", stdout=stdout)
        self.assertIn("Paid: 1", stdout.getvalue())


# ---------------------------------------------------------------------------
# Admin mark-paid restrictions
# ---------------------------------------------------------------------------


class AdminMarkPaidTests(_PayoutBase):
    def test_admin_cannot_mark_requested_payout_paid(self):
        admin = self._make_user("admin_mark", Profile.ROLE_LANDLORD, is_staff=True)
        payout = LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("1000.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="254712345678",
            status=LandlordPayout.STATUS_REQUESTED,
        )
        self._auth(admin)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 400)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_REQUESTED)

    def test_admin_can_mark_processing_payout_paid_with_audit(self):
        admin = self._make_user("admin_mark_ok", Profile.ROLE_LANDLORD, is_staff=True)
        payout = LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("1000.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="254712345678",
            status=LandlordPayout.STATUS_PROCESSING,
            processing_at=timezone.now(),
            provider_reference="dash-ref-1",
        )
        self._auth(admin)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 200, response.data)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_PAID)
        self.assertEqual(payout.marked_paid_by_id, admin.id)
        self.assertIsNotNone(payout.marked_paid_at)


# ---------------------------------------------------------------------------
# Admin reverse
# ---------------------------------------------------------------------------


class AdminReverseTests(_PayoutBase):
    def test_admin_reverse_restores_funds(self):
        admin = self._make_user("admin_reverse", Profile.ROLE_LANDLORD, is_staff=True)
        # Pretend a PROCESSING payout exists with a reservation already held.
        self.balance.available_balance = self.balance.available_balance - Decimal("3000.00")
        self.balance.save(update_fields=["available_balance"])
        payout = LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("3000.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="254712345678",
            status=LandlordPayout.STATUS_PROCESSING,
            processing_at=timezone.now(),
            provider_reference="rev-ref-1",
        )
        self._auth(admin)
        response = self.client.post(
            reverse("landlord-payout-reverse", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 200, response.data)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_REVERSED)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_balance, Decimal("20000.00"))

    def test_non_admin_cannot_reverse(self):
        payout = LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("1000.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="254712345678",
            status=LandlordPayout.STATUS_PROCESSING,
            processing_at=timezone.now(),
            provider_reference="rev-non-admin",
        )
        self._auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-reverse", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Adapter classification helper
# ---------------------------------------------------------------------------


class IntaSendOutcomeClassificationTests(APITestCase):
    def test_explicit_failed_status_is_rejected(self):
        from core.services import _classify_intasend_payout_response
        outcome, ref = _classify_intasend_payout_response({"status": "FAILED"})
        self.assertEqual(outcome, "rejected")
        self.assertIsNone(ref)

    def test_explicit_completed_status_is_settled(self):
        from core.services import _classify_intasend_payout_response
        outcome, ref = _classify_intasend_payout_response({
            "status": "COMPLETED",
            "tracking_id": "abc",
        })
        self.assertEqual(outcome, "settled")
        self.assertEqual(ref, "abc")

    def test_sent_with_tracking_id_is_accepted_not_settled(self):
        """Regression guard for the original bug: `_intasend_payout_accepted`
        used to treat ANY response with a tracking id as success → PAID."""
        from core.services import _classify_intasend_payout_response
        outcome, ref = _classify_intasend_payout_response({
            "status": "SENT",
            "tracking_id": "abc",
        })
        self.assertEqual(outcome, "accepted")  # NOT "settled"
        self.assertEqual(ref, "abc")

    def test_results_list_alone_is_accepted_not_settled(self):
        from core.services import _classify_intasend_payout_response
        outcome, ref = _classify_intasend_payout_response({
            "results": [{"tracking_id": "xyz"}]
        })
        self.assertEqual(outcome, "accepted")
        self.assertEqual(ref, "xyz")

    def test_completely_empty_response_is_ambiguous(self):
        from core.services import _classify_intasend_payout_response
        outcome, ref = _classify_intasend_payout_response({})
        self.assertEqual(outcome, "ambiguous")
        self.assertIsNone(ref)
