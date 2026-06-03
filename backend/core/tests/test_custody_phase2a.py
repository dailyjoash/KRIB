"""Phase 2A: custody float drain & cutover safety rail."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import F
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from core.models import (
    CustodyAuditLog,
    LandlordBalance,
    LandlordPayout,
    LandlordSettings,
    Profile,
)

PASSWORD = "StrongPass1234!"


@override_settings(CUSTODY_MODE_ENABLED=True)
class CustodyPhase2ABase(APITestCase):
    def make_user(self, username, role, *, is_staff=False):
        user = User.objects.create_user(username=username, password=PASSWORD)
        if is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        profile = user.profile
        profile.role = role
        profile.save(update_fields=["role"])
        return user

    def setUp(self):
        self.staff = self.make_user("c_staff", Profile.ROLE_LANDLORD, is_staff=True)
        self.landlord = self.make_user("c_ll", Profile.ROLE_LANDLORD)
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Custody Homes",
                "collection_mode": LandlordSettings.COLLECTION_CUSTODY_LEGACY,
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0712345678",
            },
        )

    def _set_balance(self, available="0.00", locked="0.00"):
        balance, _ = LandlordBalance.objects.update_or_create(
            landlord=self.landlord,
            defaults={
                "available_balance": Decimal(available),
                "locked_balance": Decimal(locked),
            },
        )
        return balance

    def _cutover_url(self):
        return reverse("staff-custody-cutover", args=[self.landlord.id])

    def _refresh_mode(self):
        return LandlordSettings.objects.get(user=self.landlord).collection_mode


class CutoverRailTests(CustodyPhase2ABase):
    def test_available_balance_blocks_cutover(self):
        self._set_balance(available="100.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._cutover_url(), {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("100", resp.json()["detail"])
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_CUSTODY_LEGACY)

    def test_locked_balance_blocks_cutover(self):
        self._set_balance(locked="42.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._cutover_url(), {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("42", resp.json()["detail"])
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_CUSTODY_LEGACY)

    def test_pending_payout_blocks_cutover(self):
        self._set_balance(available="0.00", locked="0.00")
        LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("50.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="0712345678",
            status=LandlordPayout.STATUS_REQUESTED,
            requested_by=self.staff,
        )
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._cutover_url(), {}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("in-flight", resp.json()["detail"])
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_CUSTODY_LEGACY)

    def test_zero_outstanding_allows_cutover_and_audits(self):
        # No balance row at all == zero outstanding.
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._cutover_url(), {"note": "all settled"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_DIRECT_PAYBILL)
        log = CustodyAuditLog.objects.get(
            landlord=self.landlord, action=CustodyAuditLog.ACTION_CUTOVER
        )
        self.assertEqual(log.actor, self.staff)

    def test_zero_balance_row_allows_cutover(self):
        self._set_balance(available="0.00", locked="0.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._cutover_url(), {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_DIRECT_PAYBILL)

    def test_blocked_attempt_writes_audit(self):
        self._set_balance(available="10.00")
        self.client.force_authenticate(self.staff)
        self.client.post(self._cutover_url(), {}, format="json")
        self.assertTrue(
            CustodyAuditLog.objects.filter(
                landlord=self.landlord, action=CustodyAuditLog.ACTION_CUTOVER_BLOCKED
            ).exists()
        )

    def test_non_staff_cannot_cutover(self):
        self.client.force_authenticate(self.landlord)
        resp = self.client.post(self._cutover_url(), {}, format="json")
        self.assertEqual(resp.status_code, 403)


class SelfServiceSettingsRailTests(CustodyPhase2ABase):
    def test_self_service_switch_blocked_when_balance(self):
        self._set_balance(available="500.00")
        self.client.force_authenticate(self.landlord)
        resp = self.client.patch(
            reverse("landlord-settings"),
            {"collection_mode": LandlordSettings.COLLECTION_DIRECT_PAYBILL},
            format="json",
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_CUSTODY_LEGACY)

    def test_self_service_switch_allowed_when_zero(self):
        self.client.force_authenticate(self.landlord)
        resp = self.client.patch(
            reverse("landlord-settings"),
            {"collection_mode": LandlordSettings.COLLECTION_DIRECT_PAYBILL},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_DIRECT_PAYBILL)
        self.assertTrue(
            CustodyAuditLog.objects.filter(
                landlord=self.landlord, action=CustodyAuditLog.ACTION_CUTOVER
            ).exists()
        )

    def test_switching_back_to_legacy_is_always_allowed(self):
        LandlordSettings.objects.filter(user=self.landlord).update(
            collection_mode=LandlordSettings.COLLECTION_DIRECT_PAYBILL
        )
        self._set_balance(available="999.00")  # outstanding must NOT block legacy
        self.client.force_authenticate(self.landlord)
        resp = self.client.patch(
            reverse("landlord-settings"),
            {"collection_mode": LandlordSettings.COLLECTION_CUSTODY_LEGACY},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_CUSTODY_LEGACY)


class RaceSafetyTests(CustodyPhase2ABase):
    def test_credit_during_switch_does_not_strand_funds(self):
        """A credit that lands at lock-acquisition time must be observed by the
        guard's locked read, so the switch is rejected atomically and never
        produces a switched landlord with a non-zero balance."""
        self._set_balance(available="0.00", locked="0.00")

        def credit_then_lock(landlord):
            # Simulate a concurrent credit committing just before our locked read.
            LandlordBalance.objects.filter(landlord=landlord).update(
                available_balance=F("available_balance") + Decimal("250.00")
            )
            return (
                LandlordBalance.objects.select_for_update()
                .filter(landlord=landlord)
                .first()
            )

        self.client.force_authenticate(self.staff)
        with patch("core.services._lock_landlord_balance", side_effect=credit_then_lock):
            resp = self.client.post(self._cutover_url(), {}, format="json")

        self.assertEqual(resp.status_code, 409)
        # Invariant: NOT switched (so never "switched + non-zero balance").
        self.assertEqual(self._refresh_mode(), LandlordSettings.COLLECTION_CUSTODY_LEGACY)
        # The whole switch attempt rolled back atomically — no partial state.
        balance = LandlordBalance.objects.get(landlord=self.landlord)
        self.assertEqual(balance.available_balance, Decimal("0.00"))
        self.assertTrue(
            CustodyAuditLog.objects.filter(
                landlord=self.landlord, action=CustodyAuditLog.ACTION_CUTOVER_BLOCKED
            ).exists()
        )


class SettlementEndpointTests(CustodyPhase2ABase):
    def _settle_url(self):
        return reverse("staff-custody-settle", args=[self.landlord.id])

    @patch("core.views.execute_intasend_payout")
    def test_settlement_creates_payout_and_audit(self, mock_execute):
        mock_execute.return_value = {
            "outcome": "accepted",
            "provider_reference": "REF-SETTLE-1",
            "provider_status": "PENDING",
            "redacted_response": {},
            "detail": None,
        }
        self._set_balance(available="5000.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._settle_url(), {"note": "drain"}, format="json")

        self.assertEqual(resp.status_code, 202)
        mock_execute.assert_called_once()
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_PROCESSING)
        self.assertEqual(payout.amount, Decimal("5000.00"))
        balance = LandlordBalance.objects.get(landlord=self.landlord)
        self.assertEqual(balance.available_balance, Decimal("0.00"))
        log = CustodyAuditLog.objects.get(
            landlord=self.landlord, action=CustodyAuditLog.ACTION_SETTLEMENT_PAYOUT
        )
        self.assertEqual(log.amount, Decimal("5000.00"))
        self.assertEqual(log.payout_id, payout.id)

    @patch("core.views.execute_intasend_payout")
    def test_settlement_partial_amount(self, mock_execute):
        mock_execute.return_value = {
            "outcome": "accepted",
            "provider_reference": "REF-SETTLE-2",
            "provider_status": "PENDING",
            "redacted_response": {},
            "detail": None,
        }
        self._set_balance(available="5000.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._settle_url(), {"amount": "2000.00"}, format="json")
        self.assertEqual(resp.status_code, 202)
        balance = LandlordBalance.objects.get(landlord=self.landlord)
        self.assertEqual(balance.available_balance, Decimal("3000.00"))

    def test_settlement_requires_saved_payout_method(self):
        LandlordSettings.objects.filter(user=self.landlord).update(
            payout_method="", payout_destination=""
        )
        self._set_balance(available="5000.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._settle_url(), {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_settlement_rejects_overdraw(self):
        self._set_balance(available="100.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.post(self._settle_url(), {"amount": "999.00"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_non_staff_cannot_settle(self):
        self.client.force_authenticate(self.landlord)
        resp = self.client.post(self._settle_url(), {}, format="json")
        self.assertEqual(resp.status_code, 403)


class CustodyViewsTests(CustodyPhase2ABase):
    def test_landlord_list_lists_outstanding(self):
        self._set_balance(available="123.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.get(reverse("staff-custody-landlords"))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["landlords_with_outstanding"], 1)
        self.assertEqual(Decimal(str(body["total_available_balance"])), Decimal("123.00"))

    def test_landlord_detail(self):
        self._set_balance(available="50.00", locked="5.00")
        self.client.force_authenticate(self.staff)
        resp = self.client.get(
            reverse("staff-custody-landlord-detail", args=[self.landlord.id])
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["can_cutover"])
        self.assertEqual(body["collection_mode"], LandlordSettings.COLLECTION_CUSTODY_LEGACY)

    def test_detail_non_staff_forbidden(self):
        self.client.force_authenticate(self.landlord)
        resp = self.client.get(
            reverse("staff-custody-landlord-detail", args=[self.landlord.id])
        )
        self.assertEqual(resp.status_code, 403)


class CustodyInspectCommandTests(CustodyPhase2ABase):
    def test_inspect_runs_readonly(self):
        self._set_balance(available="200.00", locked="10.00")
        out = StringIO()
        call_command("custody_inspect", stdout=out)
        text = out.getvalue()
        self.assertIn("KRIB custody float inspection", text)
        self.assertIn("total available_balance", text)
        self.assertIn("In-flight (non-final) LandlordPayouts", text)
        # Read-only: balance unchanged.
        balance = LandlordBalance.objects.get(landlord=self.landlord)
        self.assertEqual(balance.available_balance, Decimal("200.00"))
