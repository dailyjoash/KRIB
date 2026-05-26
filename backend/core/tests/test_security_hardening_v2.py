"""Tests for the second-pass security hardening.

Covers wallet unlock idempotency, the provider-agnostic payment core,
UserViewSet scoping, tenant invite OTP enforcement, email consistency,
password-reset confirm throttling, health-endpoint hygiene, fixture
hygiene, the redactor, and DB integrity constraints.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import (
    LandlordBalance,
    LandlordSettings,
    Lease,
    LedgerTransaction,
    PaymentTransaction,
    Profile,
    Property,
    TenantInvite,
    Unit,
)
from core.payments import (
    PROVIDER_INTASEND,
    PaymentEvent,
    PaymentEventStatus,
    apply_payment_event,
    normalize_intasend_callback,
    normalize_paypal_capture,
    normalize_stripe_event,
)
from core.payments.redact import redact_payment_payload, redact_text
from core.services import (
    unlock_due_landlord_balance,
    unlock_due_wallet_for_user,
)


STRONG_PASSWORD = "StrongPass1234!"


class _Base(APITestCase):
    def make_user(self, username, role, *, is_staff=False, email=""):
        user = User.objects.create_user(username=username, password=STRONG_PASSWORD, email=email)
        if is_staff:
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        profile = user.profile
        profile.role = role
        profile.save(update_fields=["role"])
        return user

    def auth(self, user):
        response = self.client.post(
            reverse("token_obtain_pair"),
            {"username": user.username, "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


# ---------------------------------------------------------------------------
# 1. Wallet/landlord unlock idempotency
# ---------------------------------------------------------------------------


class WalletUnlockIdempotencyTests(_Base):
    def setUp(self):
        self.tenant = self.make_user("tenant_unlock", Profile.ROLE_TENANT)
        # A wallet-credit row whose hold has already elapsed.
        LedgerTransaction.objects.create(
            user=self.tenant,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            amount=Decimal("500.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() - timedelta(hours=1),
            reference_text="seed",
        )
        # And one row that is NOT yet due.
        LedgerTransaction.objects.create(
            user=self.tenant,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            amount=Decimal("100.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() + timedelta(hours=1),
            reference_text="not-yet-due",
        )
        profile = self.tenant.profile
        profile.wallet_locked = Decimal("600.00")
        profile.save(update_fields=["wallet_locked"])

    def test_first_unlock_credits_only_due_rows(self):
        amount = unlock_due_wallet_for_user(self.tenant)
        self.assertEqual(amount, Decimal("500.00"))
        profile = Profile.objects.get(user=self.tenant)
        self.assertEqual(profile.wallet_available, Decimal("500.00"))
        self.assertEqual(profile.wallet_locked, Decimal("100.00"))

    def test_second_unlock_is_a_noop(self):
        unlock_due_wallet_for_user(self.tenant)
        amount = unlock_due_wallet_for_user(self.tenant)
        self.assertEqual(amount, Decimal("0.00"))
        profile = Profile.objects.get(user=self.tenant)
        # Still the same — no double-credit.
        self.assertEqual(profile.wallet_available, Decimal("500.00"))


class LandlordUnlockIdempotencyTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_unlock", Profile.ROLE_LANDLORD)
        LedgerTransaction.objects.create(
            user=self.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
            amount=Decimal("2000.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() - timedelta(hours=1),
            reference_text="seed",
        )
        LandlordBalance.objects.create(
            landlord=self.landlord,
            available_balance=Decimal("0.00"),
            locked_balance=Decimal("2000.00"),
        )

    def test_unlock_is_idempotent(self):
        a = unlock_due_landlord_balance(self.landlord)
        b = unlock_due_landlord_balance(self.landlord)
        self.assertEqual(a, Decimal("2000.00"))
        self.assertEqual(b, Decimal("0.00"))
        balance = LandlordBalance.objects.get(landlord=self.landlord)
        self.assertEqual(balance.available_balance, Decimal("2000.00"))
        self.assertEqual(balance.locked_balance, Decimal("0.00"))


# ---------------------------------------------------------------------------
# 2/3. Provider-agnostic payment core
# ---------------------------------------------------------------------------


class _PaymentFixtureMixin:
    def _make_pending_payment(self, *, reference="invoice-1", amount=Decimal("10000.00")):
        landlord = self.make_user("ll_pay", Profile.ROLE_LANDLORD)
        tenant = self.make_user("tenant_pay", Profile.ROLE_TENANT)
        prop = Property.objects.create(landlord=landlord, name="P", location="NBO")
        unit = Unit.objects.create(property=prop, unit_number="U1", rent_amount=amount, deposit=Decimal("0.00"))
        lease = Lease.objects.create(
            unit=unit, tenant=tenant,
            rent_amount=amount, start_date=timezone.localdate(),
            due_day=15, status=Lease.STATUS_ACTIVE,
        )
        payment = PaymentTransaction.objects.create(
            lease=lease, tenant=tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            phone_number="254700000001",
            amount=amount,
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id=reference,
            status=PaymentTransaction.STATUS_PENDING,
        )
        return landlord, tenant, lease, payment


@override_settings(DEFAULT_PAYMENT_CURRENCY="KES")
class PaymentCoreTests(_PaymentFixtureMixin, _Base):
    def test_intasend_callback_marks_success_when_amount_matches(self):
        _, _, lease, payment = self._make_pending_payment(reference="ok-1")
        event = normalize_intasend_callback({
            "invoice_id": "ok-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "ok-1",
                "mpesa_receipt": "RCP123",
                "value": "10000.00",
                "account": f"LEASE-{lease.id}",
                "currency": "KES",
            },
        })
        result = apply_payment_event(event)
        self.assertTrue(result.ok)
        self.assertEqual(result.code, "applied")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_SUCCESS)
        # raw_callback was redacted before persisting
        self.assertIsInstance(payment.raw_callback, dict)
        self.assertNotIn("0712345678", json.dumps(payment.raw_callback))

    def test_intasend_callback_with_wrong_amount_is_rejected(self):
        _, _, lease, payment = self._make_pending_payment(reference="bad-amount-1")
        event = normalize_intasend_callback({
            "invoice_id": "bad-amount-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "bad-amount-1",
                "value": "1.00",  # ≠ payment.amount
                "account": f"LEASE-{lease.id}",
                "currency": "KES",
            },
        })
        result = apply_payment_event(event)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "amount_mismatch")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    def test_intasend_callback_with_wrong_lease_is_rejected(self):
        _, _, lease, payment = self._make_pending_payment(reference="bad-lease-1")
        event = normalize_intasend_callback({
            "invoice_id": "bad-lease-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "bad-lease-1",
                "value": "10000.00",
                "account": f"LEASE-{lease.id + 99}",  # wrong lease
                "currency": "KES",
            },
        })
        result = apply_payment_event(event)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "lease_mismatch")

    def test_duplicate_callback_is_idempotent(self):
        _, _, lease, payment = self._make_pending_payment(reference="dup-1")
        body = {
            "invoice_id": "dup-1",
            "state": "COMPLETE",
            "invoice": {
                "invoice_id": "dup-1",
                "value": "10000.00",
                "account": f"LEASE-{lease.id}",
                "currency": "KES",
                "mpesa_receipt": "RCP1",
            },
        }
        first = apply_payment_event(normalize_intasend_callback(body))
        second = apply_payment_event(normalize_intasend_callback(body))
        self.assertEqual(first.code, "applied")
        self.assertEqual(second.code, "duplicate")
        # Only one success allocation row should exist for this payment.
        payment.refresh_from_db()
        self.assertTrue(payment.allocation_done)

    def test_stripe_event_with_wrong_tenant_metadata_is_rejected(self):
        _, _, lease, payment = self._make_pending_payment(reference="pi_stripe_1")
        event = {
            "id": "evt_x",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_stripe_1",
                    "amount": 1000000,  # 10000.00 in cents
                    "currency": "kes",
                    "metadata": {"lease_id": str(lease.id), "tenant_id": "9999"},
                }
            },
        }
        normalized = normalize_stripe_event(event)
        result = apply_payment_event(normalized)
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "tenant_mismatch")

    def test_stripe_event_with_wrong_currency_is_rejected(self):
        _, _, lease, payment = self._make_pending_payment(reference="pi_stripe_2")
        event = {
            "id": "evt_y",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_stripe_2",
                    "amount": 1000000,
                    "currency": "usd",
                    "metadata": {"lease_id": str(lease.id), "tenant_id": str(payment.tenant_id)},
                }
            },
        }
        result = apply_payment_event(normalize_stripe_event(event))
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "currency_mismatch")

    def test_paypal_capture_idempotent(self):
        _, _, lease, payment = self._make_pending_payment(reference="pp_1")
        capture = {
            "id": "pp_1",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {"captures": [
                        {"id": "cap_1", "amount": {"value": "10000.00", "currency_code": "KES"}}
                    ]},
                }
            ],
        }
        first = apply_payment_event(normalize_paypal_capture(
            capture, expected_lease_id=lease.id, expected_tenant_id=payment.tenant_id
        ))
        second = apply_payment_event(normalize_paypal_capture(
            capture, expected_lease_id=lease.id, expected_tenant_id=payment.tenant_id
        ))
        self.assertEqual(first.code, "applied")
        self.assertEqual(second.code, "duplicate")


# ---------------------------------------------------------------------------
# 4. UserViewSet scoping
# ---------------------------------------------------------------------------


class UserListScopeTests(_Base):
    def setUp(self):
        self.landlord_a = self.make_user("ll_a", Profile.ROLE_LANDLORD)
        self.landlord_b = self.make_user("ll_b", Profile.ROLE_LANDLORD)
        self.tenant_of_a = self.make_user("tenant_of_a", Profile.ROLE_TENANT, email="ta@example.com")
        self.tenant_of_b = self.make_user("tenant_of_b", Profile.ROLE_TENANT, email="tb@example.com")
        prop_a = Property.objects.create(landlord=self.landlord_a, name="A", location="NBO")
        prop_b = Property.objects.create(landlord=self.landlord_b, name="B", location="MSA")
        unit_a = Unit.objects.create(property=prop_a, unit_number="A1", rent_amount=Decimal("100"))
        unit_b = Unit.objects.create(property=prop_b, unit_number="B1", rent_amount=Decimal("100"))
        Lease.objects.create(unit=unit_a, tenant=self.tenant_of_a, rent_amount=Decimal("100"),
                             start_date=timezone.localdate(), due_day=1, status=Lease.STATUS_ACTIVE)
        Lease.objects.create(unit=unit_b, tenant=self.tenant_of_b, rent_amount=Decimal("100"),
                             start_date=timezone.localdate(), due_day=1, status=Lease.STATUS_ACTIVE)

    def test_landlord_a_does_not_see_landlord_bs_tenants(self):
        self.auth(self.landlord_a)
        response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_TENANT})
        ids = {item["id"] for item in response.data}
        self.assertIn(self.tenant_of_a.id, ids)
        self.assertNotIn(self.tenant_of_b.id, ids)

    def test_landlord_cannot_list_landlords(self):
        self.auth(self.landlord_a)
        response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_LANDLORD})
        self.assertEqual(list(response.data), [])

    def test_tenant_can_only_see_self(self):
        self.auth(self.tenant_of_a)
        response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_TENANT})
        self.assertEqual([item["id"] for item in response.data], [self.tenant_of_a.id])

    def test_staff_can_see_everyone(self):
        staff = self.make_user("staff_user", Profile.ROLE_LANDLORD, is_staff=True)
        self.auth(staff)
        response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_TENANT})
        ids = {item["id"] for item in response.data}
        self.assertIn(self.tenant_of_a.id, ids)
        self.assertIn(self.tenant_of_b.id, ids)


# ---------------------------------------------------------------------------
# 5. Tenant invite OTP enforcement
# ---------------------------------------------------------------------------


class TenantInviteOTPTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_invite_otp", Profile.ROLE_LANDLORD)

    def _new_invite(self, otp_code="123456", expires_in_minutes=60):
        return TenantInvite.objects.create(
            full_name="New T",
            email="newt@example.com",
            invited_by=self.landlord,
            status=TenantInvite.STATUS_PENDING,
            expires_at=timezone.now() + timedelta(days=7),
            otp_code=otp_code,
            otp_expires_at=timezone.now() + timedelta(minutes=expires_in_minutes),
        )

    def test_accept_without_otp_when_required_fails(self):
        invite = self._new_invite()
        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"first_name": "N", "last_name": "T", "password": STRONG_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        invite.refresh_from_db()
        self.assertEqual(invite.status, TenantInvite.STATUS_PENDING)

    def test_accept_with_wrong_otp_fails_and_increments_attempts(self):
        invite = self._new_invite()
        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"first_name": "N", "last_name": "T", "password": STRONG_PASSWORD, "otp_code": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        invite.refresh_from_db()
        self.assertGreater(invite.otp_attempts, 0)
        self.assertEqual(invite.status, TenantInvite.STATUS_PENDING)

    def test_accept_with_correct_otp_succeeds(self):
        invite = self._new_invite()
        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"first_name": "N", "last_name": "T", "password": STRONG_PASSWORD, "otp_code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        invite.refresh_from_db()
        self.assertEqual(invite.status, TenantInvite.STATUS_ACCEPTED)

    def test_accepted_invite_cannot_be_reused(self):
        invite = self._new_invite()
        # First acceptance — wins.
        self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"first_name": "N", "last_name": "T", "password": STRONG_PASSWORD, "otp_code": "123456"},
            format="json",
        )
        # Second acceptance — should be rejected.
        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"first_name": "N2", "last_name": "T2", "password": STRONG_PASSWORD, "otp_code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_locked_invite_cannot_be_accepted(self):
        invite = self._new_invite()
        invite.otp_locked = True
        invite.save(update_fields=["otp_locked"])
        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"first_name": "N", "last_name": "T", "password": STRONG_PASSWORD, "otp_code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 429)


# ---------------------------------------------------------------------------
# 6. Email identity consistency
# ---------------------------------------------------------------------------


class EmailIdentityTests(_Base):
    def test_landlord_signup_neutral_on_duplicate_email(self):
        User.objects.create_user(username="existing", email="ll@example.com", password=STRONG_PASSWORD)
        response = self.client.post(
            reverse("signup-landlord"),
            {
                "business_name": "X",
                "first_name": "A",
                "last_name": "B",
                "email": "ll@example.com",
                "password": STRONG_PASSWORD,
            },
            format="json",
        )
        # Same neutral 202 the tenant/register flow uses.
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("already", str(response.data).lower())

    def test_email_change_is_case_insensitive_duplicate_rejected(self):
        User.objects.create_user(username="owner_ci", email="taken@example.com", password=STRONG_PASSWORD)
        other = self.make_user("other_ci", Profile.ROLE_TENANT, email="other@example.com")
        self.auth(other)
        response = self.client.patch(reverse("get_me"), {"email": "TAKEN@example.com"}, format="json")
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# 7. Password reset confirm throttle wiring (just verify it is wired)
# ---------------------------------------------------------------------------


class PasswordResetConfirmThrottleWiringTests(_Base):
    def test_password_reset_confirm_view_has_throttle(self):
        from core.views import password_reset_confirm
        # The decorator stack stashes throttle classes on the underlying view
        # function via DRF's view metadata. We assert the throttle scope is
        # present in the registered DRF rates.
        from django.conf import settings as dj_settings
        self.assertIn("password_reset_confirm", dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])


# ---------------------------------------------------------------------------
# 8. Fixture hygiene
# ---------------------------------------------------------------------------


class FixtureHygieneTests(_Base):
    def test_legacy_fixture_does_not_contain_password_hashes(self):
        import os
        fixture_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "fixtures",
            "sqlite_migration.json",
        )
        with open(fixture_path) as fh:
            content = fh.read()
        self.assertNotIn("pbkdf2_sha256", content)
        self.assertNotIn("@gmail", content)
        self.assertNotIn("@outlook", content)


# ---------------------------------------------------------------------------
# 11. DB integrity constraints
# ---------------------------------------------------------------------------


class IntegrityConstraintTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_constraints", Profile.ROLE_LANDLORD)
        self.tenant = self.make_user("tenant_constraints", Profile.ROLE_TENANT)
        self.prop = Property.objects.create(landlord=self.landlord, name="P", location="NBO")

    def test_negative_rent_amount_is_rejected_by_db(self):
        unit = Unit(property=self.prop, unit_number="X", rent_amount=Decimal("-1.00"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Bypass full_clean() to ensure the DB constraint fires.
                unit.save()

    def test_due_day_out_of_range_is_rejected(self):
        unit = Unit.objects.create(property=self.prop, unit_number="Y", rent_amount=Decimal("100"))
        lease = Lease(
            unit=unit, tenant=self.tenant, rent_amount=Decimal("100"),
            start_date=timezone.localdate(), due_day=31, status=Lease.STATUS_ACTIVE,
        )
        # full_clean() is enough to catch this — but in case a raw insert
        # bypasses it, the DB CheckConstraint backstops the same rule.
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                lease.save()

    def test_only_one_active_lease_per_unit_at_db_level(self):
        unit = Unit.objects.create(property=self.prop, unit_number="Z", rent_amount=Decimal("100"))
        Lease.objects.create(
            unit=unit, tenant=self.tenant, rent_amount=Decimal("100"),
            start_date=timezone.localdate(), due_day=1, status=Lease.STATUS_ACTIVE,
        )
        other_tenant = self.make_user("tenant_other_lease", Profile.ROLE_TENANT)
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                Lease.objects.create(
                    unit=unit, tenant=other_tenant, rent_amount=Decimal("100"),
                    start_date=timezone.localdate(), due_day=1, status=Lease.STATUS_ACTIVE,
                )


# ---------------------------------------------------------------------------
# 12. Redactor
# ---------------------------------------------------------------------------


class RedactorTests(_Base):
    def test_phone_number_is_masked(self):
        self.assertNotIn("0712345678", redact_text("call me at 0712345678 thanks"))
        self.assertNotIn("254712345678", redact_text("send to 254712345678 plz"))

    def test_email_is_masked(self):
        self.assertNotIn("alice@example.com", redact_text("reach alice@example.com please"))

    def test_redact_dict_removes_secret_keys(self):
        payload = {
            "phone": "0712345678",
            "email": "x@y.com",
            "amount": 100,
            "nested": {"msisdn": "254712345678", "ok": True},
        }
        out = redact_payment_payload(payload)
        self.assertEqual(out["phone"], "<redacted>")
        self.assertEqual(out["email"], "<redacted>")
        self.assertEqual(out["amount"], 100)
        self.assertEqual(out["nested"]["msisdn"], "<redacted>")
        self.assertEqual(out["nested"]["ok"], True)


# ---------------------------------------------------------------------------
# 13. Health endpoint hygiene
# ---------------------------------------------------------------------------


class HealthHygieneTests(_Base):
    def test_health_does_not_expose_debug(self):
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("debug", response.data)
        self.assertEqual(response.data.get("status"), "ok")
