from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import (
    LandlordBalance,
    LandlordCollectionAccount,
    LandlordPayout,
    LandlordSettings,
    Lease,
    LedgerTransaction,
    PaymentRecord,
    PaymentRecordAuditLog,
    PaymentTransaction,
    Profile,
    Property,
    Unit,
    compute_lease_rent_status,
)


PASSWORD = "StrongPass1234!"


class DirectPaybillBase(APITestCase):
    def make_user(self, username, role, *, is_staff=False):
        user = User.objects.create_user(username=username, password=PASSWORD)
        if is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        profile = user.profile
        profile.role = role
        profile.phone_number = "254700000001"
        profile.save(update_fields=["role", "phone_number"])
        return user

    def setUp(self):
        self.landlord = self.make_user("direct_ll", Profile.ROLE_LANDLORD)
        self.manager = self.make_user("direct_mgr", Profile.ROLE_MANAGER)
        self.tenant = self.make_user("direct_tenant", Profile.ROLE_TENANT)
        self.other_tenant = self.make_user("other_tenant", Profile.ROLE_TENANT)
        self.staff = self.make_user("direct_staff", Profile.ROLE_LANDLORD, is_staff=True)

        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Direct Homes",
                "collection_mode": LandlordSettings.COLLECTION_DIRECT_PAYBILL,
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0712345678",
                "payout_destination_updated_at": None,
            },
        )
        self.account = LandlordCollectionAccount.objects.create(
            landlord=self.landlord,
            paybill_number="123456",
            registered_business_name="Direct Homes Ltd",
        )
        self.property = Property.objects.create(
            landlord=self.landlord,
            manager=self.manager,
            name="Direct Court",
            location="Nairobi",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number="A4",
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("0.00"),
        )
        self.lease = Lease.objects.create(
            unit=self.unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def submit_payload(self, code="QHX123ABC", amount="4000.00", phone="254799000111", lease=None):
        return {
            "lease_id": (lease or self.lease).id,
            "transaction_code": code,
            "amount": amount,
            "transaction_date": timezone.now().isoformat(),
            "phone_number": phone,
        }

    def submit_payment(self, **kwargs):
        self.auth(kwargs.pop("user", self.tenant))
        return self.client.post(reverse("payments-direct-list-submit"), self.submit_payload(**kwargs), format="json")


class DirectPaybillSubmissionTests(DirectPaybillBase):
    def test_tenant_submit_creates_pending_record_and_duplicate_code_is_db_blocked(self):
        response = self.submit_payment()
        self.assertEqual(response.status_code, 201, response.data)
        record = PaymentRecord.objects.get(transaction_code="QHX123ABC")
        self.assertEqual(record.status, PaymentRecord.STATUS_PENDING_CONFIRMATION)
        self.assertEqual(record.landlord_id, self.landlord.id)
        self.assertEqual(record.collection_account_id, self.account.id)
        self.assertEqual(record.audit_logs.filter(action=PaymentRecordAuditLog.ACTION_SUBMIT).count(), 1)

        duplicate = PaymentRecord(
            lease=self.lease,
            tenant=self.tenant,
            landlord=self.landlord,
            collection_account=self.account,
            period=timezone.localdate().strftime("%Y-%m"),
            phone_number="254711222333",
            amount=Decimal("1000.00"),
            transaction_code="QHX123ABC",
            transaction_date=timezone.now(),
            submitted_by=self.tenant,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

        duplicate_response = self.submit_payment(code="QHX123ABC")
        self.assertEqual(duplicate_response.status_code, 409)

    def test_partial_confirmation_reduces_running_balance_without_requiring_exact_amount(self):
        response = self.submit_payment(amount="4000.00")
        record_id = response.data["id"]

        self.auth(self.landlord)
        confirm = self.client.post(
            reverse("payments-direct-action", kwargs={"pk": record_id, "action": "confirm"}),
            {"note": "Seen on M-Pesa statement"},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertEqual(confirm.data["status"], PaymentRecord.STATUS_CONFIRMED)

        rent = compute_lease_rent_status(self.lease, today=self.lease.start_date.replace(day=1))
        self.assertEqual(rent["paid_sum"], Decimal("4000.00"))
        self.assertEqual(rent["balance"], Decimal("6000.00"))
        self.assertEqual(rent["status"], "PARTIAL")

    def test_landlord_rejects_with_note(self):
        response = self.submit_payment(code="QHXREJECT1", amount="2500.00")
        record_id = response.data["id"]

        self.auth(self.landlord)
        reject = self.client.post(
            reverse("payments-direct-action", kwargs={"pk": record_id, "action": "reject"}),
            {"note": "Code not visible on statement"},
            format="json",
        )
        self.assertEqual(reject.status_code, 200, reject.data)
        self.assertEqual(reject.data["status"], PaymentRecord.STATUS_REJECTED)
        self.assertEqual(reject.data["rejection_note"], "Code not visible on statement")
        self.assertEqual(
            PaymentRecordAuditLog.objects.filter(payment_record_id=record_id, action=PaymentRecordAuditLog.ACTION_REJECT).count(),
            1,
        )

    def test_tenant_or_unrelated_user_cannot_confirm_landlord_payment(self):
        response = self.submit_payment(code="QHXNOAUTH1")
        record_id = response.data["id"]

        self.auth(self.tenant)
        tenant_confirm = self.client.post(
            reverse("payments-direct-action", kwargs={"pk": record_id, "action": "confirm"}),
            {"note": "I confirm myself"},
            format="json",
        )
        self.assertEqual(tenant_confirm.status_code, 403)

        self.auth(self.other_tenant)
        other_confirm = self.client.post(
            reverse("payments-direct-action", kwargs={"pk": record_id, "action": "confirm"}),
            {"note": "Not my portfolio"},
            format="json",
        )
        self.assertEqual(other_confirm.status_code, 404)

    def test_third_party_payer_phone_is_accepted(self):
        response = self.submit_payment(code="QHXPHONE1", phone="254722333444", amount="1500.00")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["phone_number"], "254722333444")

    def test_submission_for_inactive_lease_is_recorded_and_flagged_unmatched(self):
        self.lease.status = Lease.STATUS_INACTIVE
        self.lease.end_date = timezone.localdate()
        self.lease.save()

        response = self.submit_payment(code="QHXENDED1", amount="1000.00")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], PaymentRecord.STATUS_UNMATCHED)
        self.assertIn("inactive", response.data["flagged_reason"].lower())

    def test_direct_paybill_lease_does_not_start_krib_stk_push(self):
        self.auth(self.tenant)
        response = self.client.post(
            reverse("payments-mpesa-initiate"),
            {"lease_id": self.lease.id, "phone_number": "0712345678", "amount": "1000.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("direct_pay_instructions", response.data)
        self.assertFalse(PaymentTransaction.objects.filter(lease=self.lease).exists())


class DirectPaybillReconciliationTests(DirectPaybillBase):
    def test_unmatched_record_can_be_attached_and_allocated_with_audit(self):
        self.auth(self.tenant)
        unmatched_response = self.client.post(
            reverse("payments-direct-list-submit"),
            {
                "paybill_number": self.account.paybill_number,
                "payment_reference": "UNKNOWN",
                "transaction_code": "QHXUNMATCH1",
                "amount": "3000.00",
                "transaction_date": timezone.now().isoformat(),
                "phone_number": "254733222111",
            },
            format="json",
        )
        self.assertEqual(unmatched_response.status_code, 201, unmatched_response.data)
        self.assertEqual(unmatched_response.data["status"], PaymentRecord.STATUS_UNMATCHED)

        self.auth(self.landlord)
        attach = self.client.post(
            reverse("payments-direct-attach", kwargs={"pk": unmatched_response.data["id"]}),
            {"lease_id": self.lease.id, "note": "Matched by statement narration"},
            format="json",
        )
        self.assertEqual(attach.status_code, 200, attach.data)
        self.assertEqual(attach.data["status"], PaymentRecord.STATUS_CONFIRMED)
        self.assertEqual(attach.data["allocated_amount"], "3000.00")
        rent = compute_lease_rent_status(self.lease)
        self.assertEqual(rent["balance"], Decimal("7000.00"))
        self.assertEqual(
            PaymentRecordAuditLog.objects.filter(payment_record_id=unmatched_response.data["id"], action=PaymentRecordAuditLog.ACTION_ATTACH).count(),
            1,
        )

    def test_confirmed_direct_payment_creates_no_withdrawable_landlord_balance_or_ledger(self):
        response = self.submit_payment(code="QHXNOLEDGER1", amount="5000.00")
        self.auth(self.landlord)
        confirm = self.client.post(
            reverse("payments-direct-action", kwargs={"pk": response.data["id"], "action": "confirm"}),
            {"note": "Manual confirmation"},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertFalse(LedgerTransaction.objects.filter(user=self.landlord, kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT).exists())
        self.assertFalse(LandlordBalance.objects.filter(landlord=self.landlord, available_balance__gt=0).exists())

        payout = self.client.post(
            reverse("landlord-payout-request"),
            {"amount": "1000.00", "method": LandlordPayout.METHOD_MPESA, "destination": "0712345678"},
            format="json",
        )
        self.assertEqual(payout.status_code, 400)
        self.assertEqual(payout.data["detail"], "Insufficient available balance")

    def test_revenue_report_labels_direct_legacy_and_verified_status(self):
        response = self.submit_payment(code="QHXREPORT1", amount="2000.00")
        self.auth(self.landlord)
        self.client.post(
            reverse("payments-direct-action", kwargs={"pk": response.data["id"], "action": "confirm"}),
            {"note": "Unverified account"},
            format="json",
        )
        report = self.client.get(reverse("landlord-revenue"))
        self.assertEqual(report.status_code, 200, report.data)
        self.assertEqual(report.data["direct_landlord_collected"], "0.00")
        self.assertEqual(report.data["gross_collected"], "0.00")
        self.assertEqual(report.data["unverified_direct_reported"], "2000.00")
        self.assertEqual(report.data["verified_direct_collected"], "0.00")

        self.account.verification_status = LandlordCollectionAccount.STATUS_VERIFIED
        self.account.verified_at = timezone.now()
        self.account.verified_by = self.staff
        self.account.save(update_fields=["verification_status", "verified_at", "verified_by", "updated_at"])
        verified_report = self.client.get(reverse("landlord-revenue"))
        self.assertEqual(verified_report.data["direct_landlord_collected"], "2000.00")
        self.assertEqual(verified_report.data["gross_collected"], "2000.00")
        self.assertEqual(verified_report.data["verified_direct_collected"], "2000.00")
        self.assertEqual(verified_report.data["unverified_direct_reported"], "0.00")

    def test_collection_account_edit_resets_verification_to_pending(self):
        self.account.verification_status = LandlordCollectionAccount.STATUS_VERIFIED
        self.account.verified_at = timezone.now()
        self.account.verified_by = self.staff
        self.account.save(update_fields=["verification_status", "verified_at", "verified_by", "updated_at"])

        self.auth(self.landlord)
        response = self.client.patch(
            reverse("landlord-collection-account"),
            {"registered_business_name": "Direct Homes Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.account.refresh_from_db()
        self.assertEqual(self.account.verification_status, LandlordCollectionAccount.STATUS_PENDING)
        self.assertIsNone(self.account.verified_at)

    @patch("core.views.send_manager_invite", return_value={"invite_link": "https://example.test/invite"})
    def test_direct_paybill_landlord_onboarding_gate_uses_paybill_not_payout_destination(self, _mock_send):
        LandlordSettings.objects.filter(user=self.landlord).update(payout_method="", payout_destination="")
        self.auth(self.landlord)
        response = self.client.post(
            reverse("manager-invite-create"),
            {"email": "manager-direct@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)


class CustodyFeatureInertnessTests(DirectPaybillBase):
    """Section 9: custody-only money behaviours must be inert for
    direct_paybill leases but completely unchanged for custody_legacy."""

    def setUp(self):
        super().setUp()
        # Give the direct-pay tenant a wallet balance. Under custody this
        # would auto-apply to rent; under direct_paybill it must NOT.
        profile = self.tenant.profile
        profile.wallet_available = Decimal("5000.00")
        profile.wallet_locked = Decimal("0.00")
        profile.save(update_fields=["wallet_available", "wallet_locked"])

        # A parallel legacy custody landlord + lease to prove behaviour is
        # untouched for existing landlords.
        self.legacy_landlord = self.make_user("legacy_ll", Profile.ROLE_LANDLORD)
        LandlordSettings.objects.update_or_create(
            user=self.legacy_landlord,
            defaults={
                "business_name": "Legacy Homes",
                "collection_mode": LandlordSettings.COLLECTION_CUSTODY_LEGACY,
            },
        )
        self.legacy_tenant = self.make_user("legacy_tenant", Profile.ROLE_TENANT)
        legacy_profile = self.legacy_tenant.profile
        legacy_profile.wallet_available = Decimal("5000.00")
        legacy_profile.save(update_fields=["wallet_available"])
        legacy_property = Property.objects.create(
            landlord=self.legacy_landlord, name="Legacy Court", location="Nairobi"
        )
        legacy_unit = Unit.objects.create(
            property=legacy_property, unit_number="L1", rent_amount=Decimal("10000.00")
        )
        self.legacy_lease = Lease.objects.create(
            unit=legacy_unit,
            tenant=self.legacy_tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )

    def test_wallet_auto_apply_is_inert_for_direct_paybill_lease(self):
        from core.views import _apply_wallet_to_current_rent

        applied = _apply_wallet_to_current_rent(self.lease)
        self.assertEqual(applied, Decimal("0.00"))
        # No custody PaymentTransaction, no wallet debit, no landlord credit.
        self.assertFalse(PaymentTransaction.objects.filter(lease=self.lease).exists())
        self.assertFalse(
            LedgerTransaction.objects.filter(
                user=self.tenant, kind=LedgerTransaction.KIND_WALLET_DEBIT_RENT
            ).exists()
        )
        self.assertFalse(
            LedgerTransaction.objects.filter(
                user=self.landlord, kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT
            ).exists()
        )
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("5000.00"))

    def test_wallet_auto_apply_still_works_for_legacy_lease(self):
        from core.views import _apply_wallet_to_current_rent

        applied = _apply_wallet_to_current_rent(self.legacy_lease)
        # Legacy custody behaviour is unchanged: wallet credit is applied to rent.
        self.assertEqual(applied, Decimal("5000.00"))
        self.assertTrue(
            PaymentTransaction.objects.filter(
                lease=self.legacy_lease, status=PaymentTransaction.STATUS_SUCCESS
            ).exists()
        )
        self.assertTrue(
            LedgerTransaction.objects.filter(
                user=self.legacy_tenant, kind=LedgerTransaction.KIND_WALLET_DEBIT_RENT
            ).exists()
        )
        self.legacy_tenant.profile.refresh_from_db()
        self.assertEqual(self.legacy_tenant.profile.wallet_available, Decimal("0.00"))

    def test_confirmed_direct_overpayment_does_not_create_tenant_wallet_credit(self):
        # Tenant overpays (12000 against 10000 rent) on a direct-pay lease.
        # Under custody this surplus would be parked in the KRIB wallet
        # (KIND_WALLET_CREDIT / wallet_locked). Direct-pay holds no money, so
        # there must be no wallet credit and no carry-forward float.
        response = self.submit_payment(code="QHXOVERPAY1", amount="12000.00")
        self.auth(self.landlord)
        confirm = self.client.post(
            reverse("payments-direct-action", kwargs={"pk": response.data["id"], "action": "confirm"}),
            {"note": "Overpayment"},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertFalse(
            LedgerTransaction.objects.filter(
                user=self.tenant, kind=LedgerTransaction.KIND_WALLET_CREDIT
            ).exists()
        )
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_locked, Decimal("0.00"))

    def test_dashboard_summary_does_not_auto_apply_wallet_for_direct_paybill(self):
        # A GET on the tenant dashboard must not mutate wallet/ledger state
        # for a direct-pay lease.
        self.auth(self.tenant)
        response = self.client.get(reverse("dashboard-summary"))
        self.assertEqual(response.status_code, 200, response.data)
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("5000.00"))
        self.assertFalse(PaymentTransaction.objects.filter(lease=self.lease).exists())
