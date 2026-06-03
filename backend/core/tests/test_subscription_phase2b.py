"""Phase 2B: KRIB platform-fee subscription rail.

Covers invoice generation (free tier, billed tier, vacant exclusion,
idempotency, snapshot integrity), the payment flow (mark paid, idempotent
mark-paid, mismatched amount drop), API access (tenant 403, cross-landlord
isolation), and that the FREE_TIER_THRESHOLD setting is honoured at runtime.
"""

from decimal import Decimal
from io import StringIO
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import (
    Lease,
    Notification,
    Profile,
    Property,
    SubscriptionInvoice,
    SubscriptionInvoiceAuditLog,
    Unit,
)
from core.services import (
    apply_subscription_reminders,
    current_subscription_period,
    generate_subscription_invoice_for_landlord,
    mark_subscription_invoice_paid,
)

PASSWORD = "StrongPass1234!"


def _make_user(username, role, *, is_staff=False):
    user = User.objects.create_user(username=username, password=PASSWORD)
    if is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


def _make_units_with_leases(landlord, count, *, vacant_count=0):
    """Create `count` units each with an ACTIVE lease + `vacant_count` units
    with NO active lease (vacant). Returns (property, [units])."""
    prop = Property.objects.create(
        landlord=landlord,
        name=f"Building-{landlord.username}",
        location="Nairobi",
    )
    units = []
    for i in range(count):
        unit = Unit.objects.create(
            property=prop,
            unit_number=f"A{i + 1}",
            rent_amount=Decimal("10000.00"),
        )
        tenant = _make_user(f"t_{landlord.username}_{i}", Profile.ROLE_TENANT)
        Lease.objects.create(
            unit=unit,
            tenant=tenant,
            rent_amount=Decimal("10000.00"),
            start_date="2026-01-01",
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        units.append(unit)
    for i in range(vacant_count):
        Unit.objects.create(
            property=prop,
            unit_number=f"V{i + 1}",
            rent_amount=Decimal("10000.00"),
        )
    return prop, units


# ---------------------------------------------------------------------------
# Invoice generation
# ---------------------------------------------------------------------------


class GenerateSubscriptionInvoiceTests(APITestCase):
    def setUp(self):
        self.landlord = _make_user("ll_sub", Profile.ROLE_LANDLORD)
        self.period = current_subscription_period()

    def test_free_tier_landlord_gets_zero_invoice(self):
        _make_units_with_leases(self.landlord, count=5)
        invoice, created = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertTrue(created)
        self.assertEqual(invoice.billable_units_count, 5)
        self.assertEqual(invoice.amount, Decimal("0.00"))
        self.assertEqual(invoice.status, SubscriptionInvoice.STATUS_FREE_TIER)
        self.assertEqual(invoice.line_items.count(), 5)

    def test_six_units_billed_kes_300(self):
        _make_units_with_leases(self.landlord, count=6)
        invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertEqual(invoice.billable_units_count, 6)
        self.assertEqual(invoice.amount, Decimal("300.00"))
        self.assertEqual(invoice.status, SubscriptionInvoice.STATUS_PENDING)

    def test_ten_units_billed_kes_500(self):
        _make_units_with_leases(self.landlord, count=10)
        invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertEqual(invoice.billable_units_count, 10)
        self.assertEqual(invoice.amount, Decimal("500.00"))
        self.assertEqual(invoice.status, SubscriptionInvoice.STATUS_PENDING)

    def test_vacant_units_excluded_from_count(self):
        _make_units_with_leases(self.landlord, count=6, vacant_count=4)
        invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertEqual(invoice.billable_units_count, 6)
        self.assertEqual(invoice.amount, Decimal("300.00"))

    def test_regenerate_same_period_is_idempotent(self):
        _make_units_with_leases(self.landlord, count=6)
        first, created_first = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        second, created_second = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(
                landlord=self.landlord, period=self.period
            ).count(),
            1,
        )

    def test_snapshot_integrity_changing_lease_after_does_not_alter_invoice(self):
        _, units = _make_units_with_leases(self.landlord, count=6)
        invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        # End a lease AFTER generation. The invoice must not change.
        first_unit = units[0]
        Lease.objects.filter(unit=first_unit, status=Lease.STATUS_ACTIVE).update(
            status=Lease.STATUS_INACTIVE
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.billable_units_count, 6)
        self.assertEqual(invoice.amount, Decimal("300.00"))
        # Generating again for the same period must still return the original.
        invoice2, created = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertFalse(created)
        self.assertEqual(invoice2.billable_units_count, 6)

    def test_landlord_with_no_units_gets_no_invoice(self):
        invoice, created = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        self.assertFalse(created)
        self.assertIsNone(invoice)


class FreeTierThresholdSettingTests(APITestCase):
    def setUp(self):
        self.landlord = _make_user("ll_thresh", Profile.ROLE_LANDLORD)
        self.period = current_subscription_period()

    @override_settings(SUBSCRIPTION_FREE_TIER_THRESHOLD=10)
    def test_changed_threshold_takes_effect_on_next_generation(self):
        _make_units_with_leases(self.landlord, count=6)
        invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )
        # 6 units now <= threshold 10 → free tier.
        self.assertEqual(invoice.status, SubscriptionInvoice.STATUS_FREE_TIER)
        self.assertEqual(invoice.amount, Decimal("0.00"))


# ---------------------------------------------------------------------------
# Payment flow
# ---------------------------------------------------------------------------


class SubscriptionPaymentFlowTests(APITestCase):
    def setUp(self):
        self.landlord = _make_user("ll_pay", Profile.ROLE_LANDLORD)
        self.period = current_subscription_period()
        _make_units_with_leases(self.landlord, count=6)
        self.invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )

    def test_mark_paid_idempotent_writes_one_audit(self):
        ok1, inv1 = mark_subscription_invoice_paid(
            self.invoice, paid_via="QHX111", note="first"
        )
        ok2, inv2 = mark_subscription_invoice_paid(
            self.invoice, paid_via="QHX111", note="second"
        )
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertEqual(inv1.status, SubscriptionInvoice.STATUS_PAID)
        self.assertEqual(inv2.status, SubscriptionInvoice.STATUS_PAID)
        confirmed_logs = SubscriptionInvoiceAuditLog.objects.filter(
            invoice=self.invoice,
            action=SubscriptionInvoiceAuditLog.ACTION_PAYMENT_CONFIRMED,
        )
        self.assertEqual(confirmed_logs.count(), 1)

    def test_mark_paid_writes_audit_with_paid_via(self):
        mark_subscription_invoice_paid(self.invoice, paid_via="MPX-RCT-999")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_via, "MPX-RCT-999")
        self.assertIsNotNone(self.invoice.paid_at)

    def test_free_tier_invoice_cannot_be_marked_paid(self):
        free_landlord = _make_user("ll_free", Profile.ROLE_LANDLORD)
        _make_units_with_leases(free_landlord, count=3)
        free_invoice, _ = generate_subscription_invoice_for_landlord(
            free_landlord, self.period
        )
        ok, inv = mark_subscription_invoice_paid(free_invoice, paid_via="X")
        self.assertFalse(ok)
        self.assertEqual(inv.status, SubscriptionInvoice.STATUS_FREE_TIER)


# ---------------------------------------------------------------------------
# Reminder / overdue flow
# ---------------------------------------------------------------------------


class SubscriptionReminderTests(APITestCase):
    def setUp(self):
        self.landlord = _make_user("ll_remind", Profile.ROLE_LANDLORD)
        self.period = current_subscription_period()
        _make_units_with_leases(self.landlord, count=6)
        self.invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )

    @override_settings(SUBSCRIPTION_GRACE_PERIOD_DAYS=7, SUBSCRIPTION_OVERDUE_DAYS=14)
    def test_grace_period_sends_pending_reminder(self):
        now = timezone.now()
        self.invoice.generated_at = now - timedelta(days=8)
        self.invoice.save(update_fields=["generated_at", "updated_at"])

        stats = apply_subscription_reminders(now=now)

        self.assertEqual(stats["grace_reminders"], 1)
        self.assertEqual(stats["overdue_transitions"], 0)
        self.assertTrue(
            Notification.objects.filter(
                user=self.landlord,
                title="Subscription invoice reminder",
            ).exists()
        )

    @override_settings(SUBSCRIPTION_GRACE_PERIOD_DAYS=7, SUBSCRIPTION_OVERDUE_DAYS=14)
    def test_overdue_period_flips_status_and_audits(self):
        now = timezone.now()
        self.invoice.generated_at = now - timedelta(days=15)
        self.invoice.save(update_fields=["generated_at", "updated_at"])

        stats = apply_subscription_reminders(now=now)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.STATUS_OVERDUE)
        self.assertEqual(stats["overdue_transitions"], 1)
        self.assertTrue(
            SubscriptionInvoiceAuditLog.objects.filter(
                invoice=self.invoice,
                action=SubscriptionInvoiceAuditLog.ACTION_STATUS_CHANGED,
                old_status=SubscriptionInvoice.STATUS_PENDING,
                new_status=SubscriptionInvoice.STATUS_OVERDUE,
            ).exists()
        )


# ---------------------------------------------------------------------------
# API access controls
# ---------------------------------------------------------------------------


class SubscriptionApiAccessTests(APITestCase):
    def setUp(self):
        self.landlord_a = _make_user("ll_a", Profile.ROLE_LANDLORD)
        self.landlord_b = _make_user("ll_b", Profile.ROLE_LANDLORD)
        self.tenant = _make_user("t_sub", Profile.ROLE_TENANT)
        self.period = current_subscription_period()

        _make_units_with_leases(self.landlord_a, count=6)
        _make_units_with_leases(self.landlord_b, count=7)
        self.invoice_a, _ = generate_subscription_invoice_for_landlord(
            self.landlord_a, self.period
        )
        self.invoice_b, _ = generate_subscription_invoice_for_landlord(
            self.landlord_b, self.period
        )

    def test_tenant_cannot_read_current(self):
        self.client.force_authenticate(self.tenant)
        resp = self.client.get(reverse("landlord-subscription-current"))
        self.assertEqual(resp.status_code, 403)

    def test_tenant_cannot_read_list(self):
        self.client.force_authenticate(self.tenant)
        resp = self.client.get(reverse("landlord-subscription-invoices"))
        self.assertEqual(resp.status_code, 403)

    def test_tenant_cannot_initiate_pay(self):
        self.client.force_authenticate(self.tenant)
        resp = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice_a.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_landlord_a_only_sees_own_current(self):
        self.client.force_authenticate(self.landlord_a)
        resp = self.client.get(reverse("landlord-subscription-current"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["id"], self.invoice_a.id)

    def test_landlord_a_cannot_pay_landlord_b_invoice(self):
        self.client.force_authenticate(self.landlord_a)
        resp = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice_b.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_landlord_list_only_includes_own_history(self):
        self.client.force_authenticate(self.landlord_a)
        resp = self.client.get(reverse("landlord-subscription-invoices"))
        self.assertEqual(resp.status_code, 200)
        ids = [row["id"] for row in resp.json()]
        self.assertIn(self.invoice_a.id, ids)
        self.assertNotIn(self.invoice_b.id, ids)

    def test_current_returns_null_when_no_invoice_yet(self):
        # Wipe the existing invoice to simulate "generation hasn't run".
        SubscriptionInvoice.objects.filter(landlord=self.landlord_a).delete()
        self.client.force_authenticate(self.landlord_a)
        resp = self.client.get(reverse("landlord-subscription-current"))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json())


class SubscriptionPayInitiateTests(APITestCase):
    def setUp(self):
        self.landlord = _make_user("ll_payinit", Profile.ROLE_LANDLORD)
        self.period = current_subscription_period()
        _make_units_with_leases(self.landlord, count=6)
        self.invoice, _ = generate_subscription_invoice_for_landlord(
            self.landlord, self.period
        )

    @patch("core.views._missing_intasend_env_vars", return_value=[])
    @patch("core.views.intasend_stk_push")
    def test_pay_initiates_stk_and_stores_intasend_invoice_id(self, mock_stk, _mock_env):
        mock_stk.return_value = {"success": True, "invoice_id": "INTA-12345"}
        self.client.force_authenticate(self.landlord)
        resp = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        mock_stk.assert_called_once()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.intasend_invoice_id, "INTA-12345")
        self.assertTrue(
            SubscriptionInvoiceAuditLog.objects.filter(
                invoice=self.invoice,
                action=SubscriptionInvoiceAuditLog.ACTION_PAYMENT_INITIATED,
            ).exists()
        )

    @patch("core.views._missing_intasend_env_vars", return_value=[])
    @patch("core.views.intasend_stk_push")
    def test_in_flight_invoice_rejects_second_stk_attempt(self, mock_stk, _mock_env):
        mock_stk.return_value = {"success": True, "invoice_id": "INTA-FIRST"}
        self.client.force_authenticate(self.landlord)
        first = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        second = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "payment_in_progress")
        mock_stk.assert_called_once()

    @patch("core.views._missing_intasend_env_vars", return_value=[])
    @patch("core.views.intasend_stk_push")
    def test_failed_stk_attempt_clears_in_flight_marker(self, mock_stk, _mock_env):
        mock_stk.side_effect = [
            {"success": False, "error": "provider down"},
            {"success": True, "invoice_id": "INTA-RETRY"},
        ]
        self.client.force_authenticate(self.landlord)
        first = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.invoice.refresh_from_db()
        self.assertEqual(first.status_code, 502)
        self.assertIsNone(self.invoice.payment_reference)

        second = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(second.status_code, 201, second.data)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.intasend_invoice_id, "INTA-RETRY")
        self.assertEqual(mock_stk.call_count, 2)

    @patch("core.views._missing_intasend_env_vars", return_value=[])
    @patch("core.views.intasend_stk_push")
    def test_already_paid_invoice_rejects_pay(self, mock_stk, _mock_env):
        mock_stk.return_value = {"success": True, "invoice_id": "INTA-1"}
        mark_subscription_invoice_paid(self.invoice, paid_via="QHX-PRE")
        self.client.force_authenticate(self.landlord)
        resp = self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], "already_paid")
        mock_stk.assert_not_called()

    @patch("core.views._missing_intasend_env_vars", return_value=[])
    @patch("core.views.intasend_stk_push")
    def test_callback_marks_subscription_invoice_paid_idempotently(
        self, mock_stk, _mock_env
    ):
        mock_stk.return_value = {"success": True, "invoice_id": "INTA-CB-1"}
        self.client.force_authenticate(self.landlord)
        self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )

        from core.views import _try_settle_subscription_invoice_from_callback

        # Simulate the webhook arriving twice. Only the first should transition
        # to PAID; the second is a no-op.
        callback_payload = {
            "invoice_id": "INTA-CB-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "INTA-CB-1",
                "state": "COMPLETE",
                "value": "300.00",
                "mpesa_receipt": "MPESA-RCT-7",
            },
        }
        handled1 = _try_settle_subscription_invoice_from_callback(callback_payload)
        handled2 = _try_settle_subscription_invoice_from_callback(callback_payload)
        self.assertTrue(handled1)
        self.assertTrue(handled2)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SubscriptionInvoice.STATUS_PAID)
        self.assertEqual(self.invoice.paid_via, "MPESA-RCT-7")
        # Only one PAYMENT_CONFIRMED audit row even with two callback hits.
        confirmed = SubscriptionInvoiceAuditLog.objects.filter(
            invoice=self.invoice,
            action=SubscriptionInvoiceAuditLog.ACTION_PAYMENT_CONFIRMED,
        )
        self.assertEqual(confirmed.count(), 1)

    @patch("core.views._missing_intasend_env_vars", return_value=[])
    @patch("core.views.intasend_stk_push")
    def test_callback_amount_mismatch_does_not_mark_paid(self, mock_stk, _mock_env):
        mock_stk.return_value = {"success": True, "invoice_id": "INTA-AMT-X"}
        self.client.force_authenticate(self.landlord)
        self.client.post(
            reverse("landlord-subscription-pay", args=[self.invoice.id]),
            {"phone_number": "0712345678"},
            format="json",
        )
        from core.views import _try_settle_subscription_invoice_from_callback

        handled = _try_settle_subscription_invoice_from_callback(
            {
                "invoice_id": "INTA-AMT-X",
                "state": "COMPLETE",
                "invoice": {
                    "invoice_id": "INTA-AMT-X",
                    "state": "COMPLETE",
                    "value": "10.00",  # wrong amount
                },
            }
        )
        self.assertTrue(handled)  # consumed but rejected
        self.invoice.refresh_from_db()
        self.assertNotEqual(self.invoice.status, SubscriptionInvoice.STATUS_PAID)


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------


class GenerateCommandTests(APITestCase):
    def test_command_creates_invoices_and_is_idempotent(self):
        landlord = _make_user("ll_cmd", Profile.ROLE_LANDLORD)
        _make_units_with_leases(landlord, count=6)
        out = StringIO()
        call_command("generate_subscription_invoices", stdout=out)
        text = out.getvalue()
        self.assertIn("Subscription invoice generation complete", text)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(landlord=landlord).count(), 1
        )

        # Re-run: no duplicate.
        out2 = StringIO()
        call_command("generate_subscription_invoices", stdout=out2)
        self.assertEqual(
            SubscriptionInvoice.objects.filter(landlord=landlord).count(), 1
        )

    def test_command_respects_period_argument(self):
        landlord = _make_user("ll_cmd_period", Profile.ROLE_LANDLORD)
        _make_units_with_leases(landlord, count=6)
        call_command(
            "generate_subscription_invoices",
            "--period",
            "2027-01",
            stdout=StringIO(),
        )
        invoice = SubscriptionInvoice.objects.get(landlord=landlord)
        self.assertEqual(invoice.period, "2027-01")


class SchedulerSubscriptionWiringTests(APITestCase):
    def test_apply_reminders_command_runs(self):
        out = StringIO()

        call_command("apply_subscription_reminders", stdout=out)

        self.assertIn("Subscription reminders applied", out.getvalue())

    def test_apply_reminders_command_dry_run(self):
        out = StringIO()

        with patch(
            "core.management.commands.apply_subscription_reminders.apply_subscription_reminders"
        ) as mock_apply:
            call_command("apply_subscription_reminders", "--dry-run", stdout=out)

        self.assertIn("Dry run", out.getvalue())
        mock_apply.assert_not_called()

    @override_settings(SUBSCRIPTION_BILLING_DAY=15)
    def test_generate_skipped_on_wrong_day(self):
        from core.management.commands import run_periodic_tasks

        with patch(
            "core.management.commands.run_periodic_tasks.timezone.localdate",
            return_value=date(2026, 6, 2),
        ), patch("django.core.management.call_command") as mock_call:
            results = run_periodic_tasks.run_scheduled_tasks()

        called_names = [c.args[0] for c in mock_call.call_args_list]
        self.assertNotIn("generate_subscription_invoices", called_names)
        self.assertIsNone(results["generate_subscription_invoices"])

    @override_settings(SUBSCRIPTION_BILLING_DAY=15)
    def test_generate_runs_on_billing_day(self):
        from core.management.commands import run_periodic_tasks

        with patch(
            "core.management.commands.run_periodic_tasks.timezone.localdate",
            return_value=date(2026, 6, 15),
        ), patch("django.core.management.call_command") as mock_call:
            run_periodic_tasks.run_scheduled_tasks()

        called_names = [c.args[0] for c in mock_call.call_args_list]
        self.assertIn("generate_subscription_invoices", called_names)
