"""Second-pass payout-lifecycle tests.

Covers:
  1. run_periodic_tasks runs recurring jobs and survives failures.
  2. Admin mark-paid rejects legacy PENDING, REQUESTED, PROCESSING-without-ref.
  3. Initial IntaSend SUCCESS now means ACCEPTED, not SETTLED; status-lookup
     SUCCESS still settles (because the lookup endpoint is authoritative).
"""

from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import LandlordPayout, Profile


STRONG_PASSWORD = "StrongPass1234!"


def _make_user(username, role, *, is_staff=False):
    user = User.objects.create_user(username=username, password=STRONG_PASSWORD)
    if is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


def _auth(client, user):
    response = client.post(
        reverse("token_obtain_pair"),
        {"username": user.username, "password": STRONG_PASSWORD},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


# ---------------------------------------------------------------------------
# 1. Scheduler wiring
# ---------------------------------------------------------------------------


class PeriodicTasksRunnerTests(APITestCase):
    @override_settings(SUBSCRIPTION_BILLING_DAY=1, CUSTODY_MODE_ENABLED=True)
    def test_runner_invokes_regular_tasks(self):
        """The production scheduler must call check_arrears,
        reconcile_payment_allocations, and reconcile_payouts each cycle.

        Without this, PROCESSING payouts and SUCCESS-but-unallocated
        payments would only finalize when an operator runs the command by
        hand — that's the residual the v2 brief asked us to close.
        """
        from core.management.commands import run_periodic_tasks

        with patch(
            "core.management.commands.run_periodic_tasks.timezone.localdate",
            return_value=date(2026, 6, 2),
        ), patch("django.core.management.call_command") as mock_call:
            results = run_periodic_tasks.run_scheduled_tasks()

        called_names = [c.args[0] for c in mock_call.call_args_list]
        self.assertIn("check_arrears", called_names)
        self.assertIn("reconcile_payment_allocations", called_names)
        self.assertIn("reconcile_payouts", called_names)
        self.assertIn("apply_subscription_reminders", called_names)
        self.assertNotIn("generate_subscription_invoices", called_names)
        self.assertEqual(results["check_arrears"], True)
        self.assertEqual(results["reconcile_payment_allocations"], True)
        self.assertEqual(results["reconcile_payouts"], True)
        self.assertEqual(results["apply_subscription_reminders"], True)
        self.assertIsNone(results["generate_subscription_invoices"])

    @override_settings(SUBSCRIPTION_BILLING_DAY=1, CUSTODY_MODE_ENABLED=True)
    def test_single_task_failure_does_not_block_others(self):
        """check_arrears raising must not prevent reconcile_payouts from
        running. The whole point of the per-task try/except wrapper."""
        from core.management.commands import run_periodic_tasks

        def fake_call_command(name, **kwargs):
            if name == "check_arrears":
                raise RuntimeError("boom in check_arrears")
            return 0

        with patch(
            "core.management.commands.run_periodic_tasks.timezone.localdate",
            return_value=date(2026, 6, 2),
        ), patch(
            "django.core.management.call_command",
            side_effect=fake_call_command,
        ) as mock_call:
            results = run_periodic_tasks.run_scheduled_tasks()

        # check_arrears errored…
        self.assertEqual(results["check_arrears"], False)
        # …but the others still ran and succeeded.
        self.assertEqual(results["reconcile_payment_allocations"], True)
        self.assertEqual(results["reconcile_payouts"], True)
        self.assertEqual(results["apply_subscription_reminders"], True)
        called_names = [c.args[0] for c in mock_call.call_args_list]
        self.assertIn("reconcile_payouts", called_names)

    @override_settings(SUBSCRIPTION_BILLING_DAY=1, CUSTODY_MODE_ENABLED=True)
    def test_command_once_flag_runs_one_cycle_then_exits(self):
        """`--once` lets the test suite and ad-hoc operators exercise the
        loop without hanging on time.sleep."""
        stdout = StringIO()
        with patch(
            "core.management.commands.run_periodic_tasks.timezone.localdate",
            return_value=date(2026, 6, 2),
        ), patch("django.core.management.call_command") as mock_call:
            call_command("run_periodic_tasks", "--once", stdout=stdout)
        # Four always-on tasks are attempted; billing generation is skipped.
        self.assertEqual(mock_call.call_count, 4)


# ---------------------------------------------------------------------------
# 2. Admin mark-paid restrictions
# ---------------------------------------------------------------------------


@override_settings(CUSTODY_MODE_ENABLED=True)
class AdminMarkPaidRestrictionsTests(APITestCase):
    def setUp(self):
        self.landlord = _make_user("ll_mp_v2", Profile.ROLE_LANDLORD)
        self.admin = _make_user("admin_mp_v2", Profile.ROLE_LANDLORD, is_staff=True)
        self.other = _make_user("other_mp_v2", Profile.ROLE_TENANT)

    def _payout(self, status, *, provider_reference="dash-ref"):
        return LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("1000.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="254712345678",
            status=status,
            provider_reference=provider_reference,
            processing_at=timezone.now() if status == LandlordPayout.STATUS_PROCESSING else None,
        )

    def test_legacy_pending_cannot_be_marked_paid(self):
        payout = self._payout(LandlordPayout.STATUS_PENDING, provider_reference=None)
        _auth(self.client, self.admin)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "invalid_state")
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_PENDING)

    def test_requested_cannot_be_marked_paid(self):
        payout = self._payout(LandlordPayout.STATUS_REQUESTED, provider_reference=None)
        _auth(self.client, self.admin)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "invalid_state")

    def test_processing_without_provider_reference_cannot_be_marked_paid(self):
        payout = self._payout(LandlordPayout.STATUS_PROCESSING, provider_reference="")
        _auth(self.client, self.admin)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "missing_provider_reference")
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_PROCESSING)

    def test_processing_with_reference_can_be_marked_paid_and_audited(self):
        payout = self._payout(LandlordPayout.STATUS_PROCESSING, provider_reference="dashref-1")
        _auth(self.client, self.admin)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 200, response.data)
        payout.refresh_from_db()
        self.assertEqual(payout.status, LandlordPayout.STATUS_PAID)
        self.assertEqual(payout.marked_paid_by_id, self.admin.id)
        self.assertIsNotNone(payout.marked_paid_at)

    def test_non_staff_cannot_mark_paid(self):
        payout = self._payout(LandlordPayout.STATUS_PROCESSING, provider_reference="dashref-2")
        _auth(self.client, self.other)
        response = self.client.post(
            reverse("landlord-payout-mark-paid", kwargs={"pk": payout.id})
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# 3. IntaSend classification split
# ---------------------------------------------------------------------------


class IntaSendClassificationSplitTests(APITestCase):
    """The initial payout submission must NOT treat provider "SUCCESS" as
    settled. The status lookup may.
    """

    def test_initial_success_with_tracking_id_is_accepted_not_settled(self):
        from core.services import classify_initial_intasend_payout_response
        outcome, ref = classify_initial_intasend_payout_response({
            "status": "SUCCESS",
            "tracking_id": "tx-1",
        })
        # The bug v2 closes: previously this would return "settled".
        self.assertEqual(outcome, "accepted")
        self.assertEqual(ref, "tx-1")

    def test_initial_non_empty_results_without_settled_status_is_accepted(self):
        from core.services import classify_initial_intasend_payout_response
        outcome, ref = classify_initial_intasend_payout_response({
            "results": [{"tracking_id": "tx-2"}],
        })
        self.assertEqual(outcome, "accepted")
        self.assertEqual(ref, "tx-2")

    def test_initial_explicit_completed_can_still_settle(self):
        from core.services import classify_initial_intasend_payout_response
        outcome, ref = classify_initial_intasend_payout_response({
            "status": "COMPLETED",
            "tracking_id": "tx-3",
        })
        self.assertEqual(outcome, "settled")
        self.assertEqual(ref, "tx-3")

    def test_initial_explicit_paid_can_settle(self):
        from core.services import classify_initial_intasend_payout_response
        outcome, ref = classify_initial_intasend_payout_response({
            "status": "PAID",
            "tracking_id": "tx-4",
        })
        self.assertEqual(outcome, "settled")
        self.assertEqual(ref, "tx-4")

    def test_initial_explicit_failed_is_rejected(self):
        from core.services import classify_initial_intasend_payout_response
        outcome, ref = classify_initial_intasend_payout_response({"status": "FAILED"})
        self.assertEqual(outcome, "rejected")
        self.assertIsNone(ref)

    def test_status_lookup_success_is_settled(self):
        """When the operator polls IntaSend for the current state of a
        tracking id, "SUCCESS" means the transfer has actually settled.
        This is the ONE place IntaSend SUCCESS legitimately graduates a
        payout to PAID."""
        from core.services import classify_intasend_payout_status_response
        outcome, ref = classify_intasend_payout_status_response({
            "status": "SUCCESS",
            "tracking_id": "tx-5",
        })
        self.assertEqual(outcome, "settled")
        self.assertEqual(ref, "tx-5")

    def test_status_lookup_completed_is_settled(self):
        from core.services import classify_intasend_payout_status_response
        outcome, ref = classify_intasend_payout_status_response({
            "status": "COMPLETED",
            "tracking_id": "tx-6",
        })
        self.assertEqual(outcome, "settled")

    def test_status_lookup_failed_is_rejected(self):
        from core.services import classify_intasend_payout_status_response
        outcome, ref = classify_intasend_payout_status_response({
            "status": "FAILED",
        })
        self.assertEqual(outcome, "rejected")

    def test_status_lookup_processing_stays_accepted(self):
        from core.services import classify_intasend_payout_status_response
        outcome, ref = classify_intasend_payout_status_response({
            "status": "PROCESSING",
            "tracking_id": "tx-7",
        })
        self.assertEqual(outcome, "accepted")


class ExecuteIntaSendPayoutSuccessTests(APITestCase):
    """End-to-end: when IntaSend's submission API returns the literal
    {"status": "SUCCESS", "tracking_id": "..."} body, execute_intasend_payout
    must report 'accepted' so the view sets the payout PROCESSING, not PAID.
    """

    @patch("core.services.APIService")
    def test_initial_success_response_results_in_accepted(self, mock_api_service):
        service_instance = mock_api_service.return_value
        service_instance.transfer.mpesa.return_value = {
            "status": "SUCCESS",
            "tracking_id": "real-track-1",
        }
        with patch.dict(
            "os.environ",
            {"INTASEND_API_TOKEN": "tok", "INTASEND_PUBLISHABLE_KEY": "pub"},
            clear=False,
        ):
            from core.services import execute_intasend_payout

            # The service does `payout.method == payout.METHOD_MPESA`, so
            # the stub must expose METHOD_MPESA / METHOD_BANK as attributes
            # (mirroring LandlordPayout's class-level constants).
            class _StubPayout:
                METHOD_MPESA = LandlordPayout.METHOD_MPESA
                METHOD_BANK = LandlordPayout.METHOD_BANK
                id = 1
                idempotency_key = "00000000-0000-0000-0000-000000000000"
                amount = Decimal("100.00")
                destination = "0712345678"
                bank_code = None
                method = LandlordPayout.METHOD_MPESA
                landlord = type("L", (), {"get_full_name": lambda self: "", "username": "ll"})()

            result = execute_intasend_payout(_StubPayout())

        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual(result["provider_reference"], "real-track-1")
