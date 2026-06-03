"""Tests for the second-round payment hardening:
  1. Required reconciliation fields per provider (fail closed on missing).
  2. Allocation retry on duplicate SUCCESS events.
  3. reconcile_successful_unallocated_payments service + management command.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import (
    LandlordBalance,
    LandlordSettings,
    LedgerTransaction,
    Lease,
    PaymentTransaction,
    Profile,
    Property,
    Unit,
)
from core.payments import (
    PaymentEvent,
    PaymentEventStatus,
    apply_payment_event,
    normalize_intasend_callback,
    normalize_paypal_capture,
    normalize_stripe_event,
    reconcile_successful_unallocated_payments,
)


STRONG_PASSWORD = "StrongPass1234!"


class _PaymentFixtureBase(APITestCase):
    def setUp(self):
        self.landlord = self._make_user("ll_pay_recon", Profile.ROLE_LANDLORD)
        self.tenant = self._make_user("tenant_pay_recon", Profile.ROLE_TENANT)
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Payment Recon LL",
                "collection_mode": LandlordSettings.COLLECTION_CUSTODY_LEGACY,
            },
        )
        prop = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        unit = Unit.objects.create(
            property=prop, unit_number="U1",
            rent_amount=Decimal("10000.00"), deposit=Decimal("0.00"),
        )
        self.lease = Lease.objects.create(
            unit=unit, tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(), due_day=15,
            status=Lease.STATUS_ACTIVE,
        )

    def _make_user(self, username, role):
        user = User.objects.create_user(username=username, password=STRONG_PASSWORD)
        profile = user.profile
        profile.role = role
        profile.save(update_fields=["role"])
        return user

    def _make_pending(self, *, reference, amount=Decimal("10000.00"), method=PaymentTransaction.METHOD_MPESA):
        return PaymentTransaction.objects.create(
            lease=self.lease,
            tenant=self.tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            phone_number="254700000001",
            amount=amount,
            payment_method=method,
            checkout_request_id=reference,
            status=PaymentTransaction.STATUS_PENDING,
        )


# ---------------------------------------------------------------------------
# 1. Missing-required-field gates
# ---------------------------------------------------------------------------


@override_settings(DEFAULT_PAYMENT_CURRENCY="KES")
class RequiredFieldGatesTests(_PaymentFixtureBase):
    def test_intasend_success_with_missing_amount_is_rejected(self):
        payment = self._make_pending(reference="in-missing-amount")
        event = normalize_intasend_callback({
            "invoice_id": "in-missing-amount",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "in-missing-amount",
                # value intentionally omitted → amount=None
                "account": f"LEASE-{self.lease.id}",
                "currency": "KES",
                "mpesa_receipt": "R1",
            },
        })
        result = apply_payment_event(event)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_amount")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)
        self.assertFalse(
            LedgerTransaction.objects.filter(
                reference_text__contains=f"payment:{payment.id}"
            ).exists()
        )

    def test_intasend_success_with_missing_currency_is_rejected(self):
        # Force currency=None by handing the normalizer a non-mapping invoice.
        event = PaymentEvent(
            provider="intasend",
            provider_reference="in-missing-currency",
            merchant_reference="in-missing-currency",
            status=PaymentEventStatus.SUCCESS,
            amount=Decimal("10000.00"),
            currency=None,
            lease_id=self.lease.id,
            required_for_success=frozenset({"lease_id"}),
        )
        payment = self._make_pending(reference="in-missing-currency")
        result = apply_payment_event(event)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_currency")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_intasend_success_with_missing_lease_id_is_rejected(self):
        payment = self._make_pending(reference="in-missing-lease")
        event = normalize_intasend_callback({
            "invoice_id": "in-missing-lease",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "in-missing-lease",
                "value": "10000.00",
                # account narrative intentionally omitted → lease_id=None
                "currency": "KES",
            },
        })
        result = apply_payment_event(event)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_lease_id")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_stripe_success_with_missing_lease_id_metadata_is_rejected(self):
        payment = self._make_pending(
            reference="pi_missing_lease",
            method=PaymentTransaction.METHOD_CARD,
        )
        event = {
            "id": "evt_no_lease",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_missing_lease",
                    "amount": 1000000,
                    "currency": "kes",
                    "metadata": {"tenant_id": str(self.tenant.id)},
                }
            },
        }
        result = apply_payment_event(normalize_stripe_event(event))
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_lease_id")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_stripe_success_with_missing_tenant_id_metadata_is_rejected(self):
        payment = self._make_pending(
            reference="pi_missing_tenant",
            method=PaymentTransaction.METHOD_CARD,
        )
        event = {
            "id": "evt_no_tenant",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_missing_tenant",
                    "amount": 1000000,
                    "currency": "kes",
                    "metadata": {"lease_id": str(self.lease.id)},
                }
            },
        }
        result = apply_payment_event(normalize_stripe_event(event))
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_tenant_id")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_paypal_success_with_missing_amount_is_rejected(self):
        payment = self._make_pending(
            reference="pp_missing_amount",
            method=PaymentTransaction.METHOD_PAYPAL,
        )
        capture = {
            "id": "pp_missing_amount",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {"captures": [
                        {"id": "cap_x", "amount": {"currency_code": "KES"}}  # no value
                    ]}
                }
            ],
        }
        normalized = normalize_paypal_capture(
            capture, expected_lease_id=self.lease.id, expected_tenant_id=self.tenant.id
        )
        result = apply_payment_event(normalized)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_amount")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_paypal_success_with_missing_currency_is_rejected(self):
        payment = self._make_pending(
            reference="pp_missing_currency",
            method=PaymentTransaction.METHOD_PAYPAL,
        )
        capture = {
            "id": "pp_missing_currency",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {"captures": [
                        {"id": "cap_y", "amount": {"value": "10000.00"}}  # no currency_code
                    ]}
                }
            ],
        }
        normalized = normalize_paypal_capture(
            capture, expected_lease_id=self.lease.id, expected_tenant_id=self.tenant.id
        )
        result = apply_payment_event(normalized)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "missing_currency")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_valid_complete_event_still_succeeds(self):
        """Sanity check: tightening required fields must not break the
        happy-path. A fully-populated IntaSend SUCCESS still allocates."""
        payment = self._make_pending(reference="happy-path-1")
        event = normalize_intasend_callback({
            "invoice_id": "happy-path-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "happy-path-1",
                "value": "10000.00",
                "account": f"LEASE-{self.lease.id}",
                "currency": "KES",
                "mpesa_receipt": "R-OK",
            },
        })
        result = apply_payment_event(event)
        self.assertTrue(result.ok, result)
        self.assertEqual(result.code, "applied")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_SUCCESS)
        self.assertTrue(payment.allocation_done)


# ---------------------------------------------------------------------------
# 2. Allocation retry on duplicate SUCCESS event
# ---------------------------------------------------------------------------


@override_settings(DEFAULT_PAYMENT_CURRENCY="KES")
class AllocationRetryTests(_PaymentFixtureBase):
    def _build_event(self, reference):
        return normalize_intasend_callback({
            "invoice_id": reference,
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": reference,
                "value": "10000.00",
                "account": f"LEASE-{self.lease.id}",
                "currency": "KES",
                "mpesa_receipt": "R-RETRY",
            },
        })

    def test_first_event_with_allocation_failure_leaves_payment_unallocated(self):
        payment = self._make_pending(reference="retry-1")

        def boom(_payment):
            raise RuntimeError("simulated allocation crash")

        with patch("core.views._allocate_success_payment", side_effect=boom):
            result = apply_payment_event(self._build_event("retry-1"))

        self.assertTrue(result.ok)
        self.assertEqual(result.code, "applied")
        payment.refresh_from_db()
        # Payment is still SUCCESS (the lock-window save committed), but the
        # ledger work crashed. allocation_done remains False — the broken
        # state we now must be able to repair.
        self.assertEqual(payment.status, PaymentTransaction.STATUS_SUCCESS)
        self.assertFalse(payment.allocation_done)
        self.assertFalse(
            LedgerTransaction.objects.filter(
                reference_text__contains=f"payment:{payment.id};lease:{self.lease.id}"
            ).exists()
        )

    def test_duplicate_event_retries_allocation_for_unallocated_success(self):
        payment = self._make_pending(reference="retry-2")

        with patch(
            "core.views._allocate_success_payment",
            side_effect=RuntimeError("crash once"),
        ):
            apply_payment_event(self._build_event("retry-2"))

        payment.refresh_from_db()
        self.assertFalse(payment.allocation_done)

        # Second event: same body. Allocation must now run for real and
        # the result code must be "allocation_retried" so view-layer
        # receipt/SMS does NOT fire a second time.
        result = apply_payment_event(self._build_event("retry-2"))
        self.assertTrue(result.ok)
        self.assertEqual(result.code, "allocation_retried")
        payment.refresh_from_db()
        self.assertTrue(payment.allocation_done)

        # Exactly one landlord-credit ledger row for this payment, not two.
        credit_rows = LedgerTransaction.objects.filter(
            user=self.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
            reference_text__contains=f"payment:{payment.id};lease:{self.lease.id}",
        )
        self.assertEqual(credit_rows.count(), 1)

    def test_third_event_after_successful_retry_is_a_clean_duplicate(self):
        payment = self._make_pending(reference="retry-3")

        with patch(
            "core.views._allocate_success_payment",
            side_effect=RuntimeError("crash once"),
        ):
            apply_payment_event(self._build_event("retry-3"))
        # Successful retry
        apply_payment_event(self._build_event("retry-3"))
        # Third call: fully allocated already → "duplicate", no extra ledger rows.
        result = apply_payment_event(self._build_event("retry-3"))
        self.assertEqual(result.code, "duplicate")
        credit_rows = LedgerTransaction.objects.filter(
            kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
            reference_text__contains=f"payment:{payment.id};lease:{self.lease.id}",
        )
        self.assertEqual(credit_rows.count(), 1)

    def test_view_layer_skips_sms_on_allocation_retried(self):
        """The IntaSend view triggers send_sms / receipt only when the
        payment core reports a first-time `applied` transition. A retry
        of a previously-failed allocation must NOT re-fire the SMS."""
        self._make_pending(reference="retry-view-1")

        # First call: allocation crashes. The view still attempts SMS once.
        with patch("core.views._allocate_success_payment", side_effect=RuntimeError("boom")), \
             patch("core.views.send_sms") as mock_sms, \
             patch("core.views.save_payment_receipt") as mock_receipt:
            self.client.post(
                reverse("stk-callback"),
                data=self._signed_body("retry-view-1"),
                content_type="application/json",
                HTTP_X_INTASEND_SIGNATURE=self._sign(self._signed_body("retry-view-1")),
            )
        self.assertEqual(mock_sms.call_count, 1)

        # Second call: same event. allocation_retried → no extra SMS.
        with patch("core.views.send_sms") as mock_sms_2, \
             patch("core.views.save_payment_receipt") as mock_receipt_2:
            self.client.post(
                reverse("stk-callback"),
                data=self._signed_body("retry-view-1"),
                content_type="application/json",
                HTTP_X_INTASEND_SIGNATURE=self._sign(self._signed_body("retry-view-1")),
            )
        mock_sms_2.assert_not_called()
        mock_receipt_2.assert_not_called()

    # Helpers ----------------------------------------------------------------
    def _signed_body(self, reference):
        import json
        return json.dumps({
            "invoice_id": reference,
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": reference,
                "value": "10000.00",
                "account": f"LEASE-{self.lease.id}",
                "currency": "KES",
                "mpesa_receipt": "R-VIEW",
            },
        })

    def _sign(self, body):
        import hashlib
        import hmac
        import os
        secret = os.getenv("INTASEND_WEBHOOK_SECRET", "test-secret")
        return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# 3. reconcile_successful_unallocated_payments + management command
# ---------------------------------------------------------------------------


class ReconciliationServiceTests(_PaymentFixtureBase):
    def _make_orphan_success(self, reference):
        # A payment that is SUCCESS in the DB but never had ledger allocation
        # completed — the exact state a crashed _allocate_success_payment
        # leaves behind. We poke this directly to avoid having to wire up a
        # provider event.
        return PaymentTransaction.objects.create(
            lease=self.lease,
            tenant=self.tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            phone_number="254700000001",
            amount=Decimal("10000.00"),
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id=reference,
            status=PaymentTransaction.STATUS_SUCCESS,
            transaction_date=timezone.now(),
            allocation_done=False,
        )

    def test_service_retries_an_orphan_successful_payment(self):
        orphan = self._make_orphan_success("orphan-1")
        stats = reconcile_successful_unallocated_payments()
        self.assertEqual(stats["retried"], 1)
        self.assertEqual(stats["ok"], 1)
        self.assertEqual(stats["failed"], 0)
        orphan.refresh_from_db()
        self.assertTrue(orphan.allocation_done)

    def test_service_skips_already_allocated_payments(self):
        # Build a fully-allocated success payment by running a healthy event.
        payment = self._make_pending(reference="already-allocated-1")
        event = normalize_intasend_callback({
            "invoice_id": "already-allocated-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "already-allocated-1",
                "value": "10000.00",
                "account": f"LEASE-{self.lease.id}",
                "currency": "KES",
            },
        })
        apply_payment_event(event)
        payment.refresh_from_db()
        self.assertTrue(payment.allocation_done)

        # Reconciliation should not touch this payment.
        rows_before = LedgerTransaction.objects.filter(user=self.landlord).count()
        stats = reconcile_successful_unallocated_payments()
        rows_after = LedgerTransaction.objects.filter(user=self.landlord).count()
        self.assertEqual(stats["retried"], 0)
        self.assertEqual(rows_after, rows_before)

    def test_service_records_failure_when_allocation_keeps_failing(self):
        self._make_orphan_success("orphan-keeps-failing")
        with patch(
            "core.views._allocate_success_payment",
            side_effect=RuntimeError("still broken"),
        ):
            stats = reconcile_successful_unallocated_payments()
        self.assertEqual(stats["retried"], 1)
        self.assertEqual(stats["ok"], 0)
        self.assertEqual(stats["failed"], 1)

    def test_management_command_runs_and_reports(self):
        self._make_orphan_success("cmd-orphan-1")
        stdout = StringIO()
        call_command("reconcile_payment_allocations", stdout=stdout)
        output = stdout.getvalue()
        self.assertIn("Retried: 1", output)
        self.assertIn("OK: 1", output)
        self.assertIn("Failed: 0", output)
