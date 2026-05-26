"""Tests covering the security-hardening fixes.

These exist in their own module so the diff reviewer can quickly see which
behaviours each remediation guarantees.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import (
    Document,
    LandlordBalance,
    LandlordPayout,
    LandlordSettings,
    Lease,
    PaymentTransaction,
    Profile,
    Property,
    Unit,
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


class PasswordPolicyTests(_Base):
    """Signup/invite accept endpoints must enforce the new min-12 length and
    block common passwords. The shared validator runs everywhere passwords
    are accepted, so we exercise every entry point."""

    def test_register_rejects_short_password(self):
        response = self.client.post(
            reverse("auth-register"),
            {
                "name": "Short Pwd",
                "email": "short@example.com",
                "role": Profile.ROLE_TENANT,
                "password": "abc12345",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_register_rejects_common_password(self):
        response = self.client.post(
            reverse("auth-register"),
            {
                "name": "Common Pwd",
                "email": "common@example.com",
                "role": Profile.ROLE_TENANT,
                "password": "password1234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_register_accepts_strong_password(self):
        response = self.client.post(
            reverse("auth-register"),
            {
                "name": "Strong Pwd",
                "email": "strong@example.com",
                "role": Profile.ROLE_TENANT,
                "password": STRONG_PASSWORD,
            },
            format="json",
        )
        self.assertIn(response.status_code, (201, 202))

    def test_landlord_signup_rejects_short_password(self):
        response = self.client.post(
            reverse("signup-landlord"),
            {
                "business_name": "Short",
                "first_name": "Amos",
                "last_name": "K",
                "password": "Qaz12345",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class AccountEnumerationTests(_Base):
    def test_register_does_not_reveal_existing_email(self):
        self.make_user("victim", Profile.ROLE_TENANT, email="victim@example.com")
        response = self.client.post(
            reverse("auth-register"),
            {
                "name": "New User",
                "email": "victim@example.com",
                "role": Profile.ROLE_TENANT,
                "password": STRONG_PASSWORD,
            },
            format="json",
        )
        # Neutral status that doesn't differentiate "created" from "exists";
        # the response body must not include the legacy "Email already registered" text.
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("Email already registered", str(response.data))


class EmailChangeUniquenessTests(_Base):
    def test_cannot_change_email_to_one_already_in_use(self):
        owner = self.make_user("owner_acc", Profile.ROLE_TENANT, email="taken@example.com")
        other = self.make_user("other_acc", Profile.ROLE_TENANT, email="other@example.com")
        self.auth(other)
        response = self.client.patch(reverse("get_me"), {"email": "taken@example.com"}, format="json")
        self.assertEqual(response.status_code, 400)
        owner.refresh_from_db()
        self.assertEqual(owner.email, "taken@example.com")

    def test_can_keep_my_own_email(self):
        user = self.make_user("self_email", Profile.ROLE_TENANT, email="self@example.com")
        self.auth(user)
        response = self.client.patch(reverse("get_me"), {"email": "self@example.com"}, format="json")
        self.assertEqual(response.status_code, 200)


@override_settings(
    INTASEND_WEBHOOK_SECRET="ci-only-intasend-webhook-secret-please-replace-1234567890",
)
class StripeWebhookFailClosedTests(_Base):
    def test_stripe_webhook_rejects_when_secret_missing(self):
        # No STRIPE_WEBHOOK_SECRET configured (default). The endpoint must
        # refuse rather than process an unsigned event.
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz", "STRIPE_WEBHOOK_SECRET": ""}, clear=False):
            response = self.client.post(
                reverse("payments-stripe-webhook"),
                data=json.dumps({"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_x"}}}),
                content_type="application/json",
            )
        # Either 503 (secret missing) or 400 (stripe SDK rejects); both are
        # fail-closed. The critical assertion is the response did not return 200.
        self.assertIn(response.status_code, (400, 503))


class LandlordPayoutDestinationGuardTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_payout_guard", Profile.ROLE_LANDLORD)
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Test LL",
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0712345678",
            },
        )
        LandlordBalance.objects.create(
            landlord=self.landlord,
            available_balance=Decimal("20000.00"),
            locked_balance=Decimal("0.00"),
        )

    @patch("core.views.execute_intasend_payout")
    def test_payout_to_unsaved_destination_is_rejected(self, mock_execute):
        self.auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "5000.00",
                "method": LandlordPayout.METHOD_MPESA,
                "destination": "0799999999",  # not the saved 0712345678
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("code"), "destination_not_verified")
        mock_execute.assert_not_called()
        # Balance must not have been debited.
        self.landlord.landlord_balance.refresh_from_db()
        self.assertEqual(self.landlord.landlord_balance.available_balance, Decimal("20000.00"))

    @patch("core.views.execute_intasend_payout")
    def test_payout_to_saved_destination_is_accepted(self, mock_execute):
        # Settled outcome → PAID (201). The destination-guard test does not
        # care whether the payout ends as PAID or PROCESSING; it cares that
        # the destination matched and the provider was called.
        mock_execute.return_value = {
            "outcome": "settled",
            "provider_reference": "ok-ref-1",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {"status": "COMPLETED"},
        }
        self.auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "5000.00",
                "method": LandlordPayout.METHOD_MPESA,
                "destination": "0712345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    @patch("core.views.execute_intasend_payout")
    def test_payout_destination_normalization(self, mock_execute):
        mock_execute.return_value = {
            "outcome": "settled",
            "provider_reference": "norm-ref",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {"status": "COMPLETED"},
        }
        # The saved destination ("0712345678") and the submitted destination
        # ("+254712345678") differ in surface form but normalize to the same
        # MSISDN. The guard must accept that.
        self.auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "1000.00",
                "method": LandlordPayout.METHOD_MPESA,
                "destination": "+254712345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_bank_payout_requires_saved_bank_code_match(self):
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Test LL",
                "payout_method": LandlordPayout.METHOD_BANK,
                "payout_destination": "1234567890",
                "payout_bank_code": "01",
            },
        )
        self.auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "5000.00",
                "method": LandlordPayout.METHOD_BANK,
                "destination": "1234567890",
                "bank_code": "99",  # wrong bank code
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class PayoutMarkPaidAuditTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_audit", Profile.ROLE_LANDLORD)
        self.admin = self.make_user("admin_audit", Profile.ROLE_LANDLORD, is_staff=True)
        # Admin mark-paid only works for PROCESSING payouts now (provider
        # already accepted with a provider_reference). The previous PENDING
        # value was a transitional legacy state and is no longer the
        # representative case.
        self.payout = LandlordPayout.objects.create(
            landlord=self.landlord,
            amount=Decimal("1000.00"),
            method=LandlordPayout.METHOD_MPESA,
            destination="0712345678",
            status=LandlordPayout.STATUS_PROCESSING,
            provider_reference="audit-ref-1",
            processing_at=timezone.now(),
        )

    def test_mark_paid_records_auditor_and_blocks_replay(self):
        self.auth(self.admin)
        url = reverse("landlord-payout-mark-paid", kwargs={"pk": self.payout.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, LandlordPayout.STATUS_PAID)
        self.assertEqual(self.payout.marked_paid_by, self.admin)
        self.assertIsNotNone(self.payout.marked_paid_at)

        # Second call must not double-credit; we now return 400.
        replay = self.client.post(url)
        self.assertEqual(replay.status_code, 400)


class TenantDocumentScopeTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_doc", Profile.ROLE_LANDLORD)
        self.tenant_a = self.make_user("tenant_doc_a", Profile.ROLE_TENANT)
        self.tenant_b = self.make_user("tenant_doc_b", Profile.ROLE_TENANT)
        self.property = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        unit_a = Unit.objects.create(property=self.property, unit_number="A", rent_amount=Decimal("100"))
        unit_b = Unit.objects.create(property=self.property, unit_number="B", rent_amount=Decimal("100"))
        self.lease_a = Lease.objects.create(
            unit=unit_a, tenant=self.tenant_a,
            rent_amount=Decimal("100"), start_date=timezone.localdate(),
            status=Lease.STATUS_ACTIVE, due_day=1,
        )
        self.lease_b = Lease.objects.create(
            unit=unit_b, tenant=self.tenant_b,
            rent_amount=Decimal("100"), start_date=timezone.localdate(),
            status=Lease.STATUS_ACTIVE, due_day=1,
        )
        self.doc_b = Document.objects.create(
            property=self.property,
            lease=self.lease_b,
            tenant=self.tenant_b,
            uploaded_by=self.landlord,
            document_type=Document.TYPE_LEASE,
            file_path=SimpleUploadedFile("lease_b.pdf", b"%PDF-1.4 lease b", content_type="application/pdf"),
        )

    def test_tenant_a_does_not_see_tenant_b_document_in_list(self):
        self.auth(self.tenant_a)
        response = self.client.get(reverse("documents-list"))
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data}
        self.assertNotIn(self.doc_b.id, ids)

    def test_tenant_a_cannot_download_tenant_b_document(self):
        self.auth(self.tenant_a)
        response = self.client.get(reverse("documents-download", kwargs={"pk": self.doc_b.id}))
        self.assertEqual(response.status_code, 403)

    def test_tenant_b_can_download_own_document(self):
        self.auth(self.tenant_b)
        response = self.client.get(reverse("documents-download", kwargs={"pk": self.doc_b.id}))
        self.assertEqual(response.status_code, 200)
        # Force attachment so the browser never inline-renders an uploaded file.
        self.assertEqual(response.headers.get("Content-Disposition", "").split(";")[0].strip(), "attachment")


class MediaProxyTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_media", Profile.ROLE_LANDLORD)
        self.tenant = self.make_user("tenant_media", Profile.ROLE_TENANT)
        self.outsider = self.make_user("outsider_media", Profile.ROLE_TENANT)
        prop = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        unit = Unit.objects.create(property=prop, unit_number="A", rent_amount=Decimal("100"))
        self.lease = Lease.objects.create(
            unit=unit, tenant=self.tenant,
            rent_amount=Decimal("100"), start_date=timezone.localdate(),
            status=Lease.STATUS_ACTIVE, due_day=1,
        )
        self.doc = Document.objects.create(
            property=prop,
            lease=self.lease,
            tenant=self.tenant,
            uploaded_by=self.landlord,
            document_type=Document.TYPE_LEASE,
            file_path=SimpleUploadedFile("private.pdf", b"%PDF-1.4 secret", content_type="application/pdf"),
        )

    def test_anonymous_cannot_reach_media_proxy(self):
        response = self.client.get(f"/media/{self.doc.file_path.name}")
        self.assertIn(response.status_code, (401, 403))

    def test_unrelated_tenant_cannot_reach_media_proxy(self):
        self.auth(self.outsider)
        response = self.client.get(f"/media/{self.doc.file_path.name}")
        self.assertEqual(response.status_code, 403)

    def test_owner_can_reach_media_proxy_with_attachment_disposition(self):
        self.auth(self.tenant)
        response = self.client.get(f"/media/{self.doc.file_path.name}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers.get("Content-Disposition", "").startswith("attachment"),
        )

    def test_media_proxy_rejects_traversal(self):
        self.auth(self.tenant)
        response = self.client.get("/media/../etc/passwd")
        # Django collapses .. before our view runs, so this becomes a non-match.
        self.assertIn(response.status_code, (301, 404))


class FileUploadHardeningTests(_Base):
    def setUp(self):
        self.landlord = self.make_user("ll_upload", Profile.ROLE_LANDLORD)
        self.property = Property.objects.create(landlord=self.landlord, name="P", location="NBO")

    def test_html_disguised_as_pdf_is_rejected(self):
        self.auth(self.landlord)
        evil = SimpleUploadedFile(
            "fake.pdf",
            b"<html><body><script>alert(1)</script></body></html>",
            content_type="application/pdf",
        )
        response = self.client.post(
            reverse("documents-upload"),
            {"property": self.property.id, "document_type": Document.TYPE_OTHER, "file_path": evil},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_svg_disguised_as_png_is_rejected(self):
        self.auth(self.landlord)
        evil = SimpleUploadedFile(
            "fake.png",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>',
            content_type="image/png",
        )
        response = self.client.post(
            reverse("documents-upload"),
            {"property": self.property.id, "document_type": Document.TYPE_OTHER, "file_path": evil},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


class IDORScopeTests(_Base):
    def setUp(self):
        self.landlord_a = self.make_user("ll_idor_a", Profile.ROLE_LANDLORD)
        self.landlord_b = self.make_user("ll_idor_b", Profile.ROLE_LANDLORD)
        self.property_a = Property.objects.create(landlord=self.landlord_a, name="A", location="NBO")
        self.property_b = Property.objects.create(landlord=self.landlord_b, name="B", location="MSA")
        self.unit_a = Unit.objects.create(property=self.property_a, unit_number="A1", rent_amount=Decimal("100"))
        self.unit_b = Unit.objects.create(property=self.property_b, unit_number="B1", rent_amount=Decimal("100"))

    def test_landlord_cannot_move_unit_to_other_property(self):
        self.auth(self.landlord_a)
        response = self.client.patch(
            reverse("units-detail", kwargs={"pk": self.unit_a.id}),
            {"property_id": self.property_b.id},
            format="json",
        )
        # Either DRF rejects via the scoped queryset (400) or perform_update
        # rejects (403). Both are acceptable; the critical assertion is the
        # unit stayed put.
        self.assertIn(response.status_code, (400, 403))
        self.unit_a.refresh_from_db()
        self.assertEqual(self.unit_a.property_id, self.property_a.id)

    def test_landlord_cannot_create_lease_pointing_at_other_landlords_unit(self):
        tenant = self.make_user("tenant_idor", Profile.ROLE_TENANT)
        self.auth(self.landlord_a)
        response = self.client.post(
            reverse("leases-list"),
            {
                "unit_id": self.unit_b.id,
                "tenant_id": tenant.id,
                "rent_amount": "100.00",
                "start_date": str(timezone.localdate()),
            },
            format="json",
        )
        self.assertIn(response.status_code, (400, 403))


class CrossLandlordTenantScopeTests(_Base):
    """A landlord must not be able to attach another landlord's tenant to a
    lease they create on their own unit."""

    def setUp(self):
        self.landlord_a = self.make_user("ll_xt_a", Profile.ROLE_LANDLORD)
        self.landlord_b = self.make_user("ll_xt_b", Profile.ROLE_LANDLORD)
        self.tenant_of_b = self.make_user("tenant_of_b", Profile.ROLE_TENANT, email="tenant_b@example.com")
        # tenant_of_b is on a lease in landlord_b's portfolio.
        prop_b = Property.objects.create(landlord=self.landlord_b, name="B", location="MSA")
        unit_b = Unit.objects.create(property=prop_b, unit_number="B1", rent_amount=Decimal("100"))
        Lease.objects.create(
            unit=unit_b, tenant=self.tenant_of_b,
            rent_amount=Decimal("100"), start_date=timezone.localdate(),
            status=Lease.STATUS_ACTIVE, due_day=1,
        )
        # landlord_a has their own unit but has never invited tenant_of_b.
        self.prop_a = Property.objects.create(landlord=self.landlord_a, name="A", location="NBO")
        self.unit_a = Unit.objects.create(property=self.prop_a, unit_number="A1", rent_amount=Decimal("100"))

    def test_landlord_a_cannot_attach_landlord_bs_tenant(self):
        self.auth(self.landlord_a)
        response = self.client.post(
            reverse("leases-list"),
            {
                "unit_id": self.unit_a.id,
                "tenant_id": self.tenant_of_b.id,
                "rent_amount": "100.00",
                "start_date": str(timezone.localdate()),
            },
            format="json",
        )
        self.assertIn(response.status_code, (400, 403))
        self.assertFalse(Lease.objects.filter(unit=self.unit_a, tenant=self.tenant_of_b).exists())


class CrossLandlordManagerScopeTests(_Base):
    """A landlord must not be able to assign another landlord's manager to
    one of their own properties without first inviting them."""

    def setUp(self):
        self.landlord_a = self.make_user("ll_xm_a", Profile.ROLE_LANDLORD)
        self.landlord_b = self.make_user("ll_xm_b", Profile.ROLE_LANDLORD)
        self.manager_of_a = self.make_user("manager_of_a", Profile.ROLE_MANAGER, email="mgr_a@example.com")
        Property.objects.create(landlord=self.landlord_a, manager=self.manager_of_a, name="A", location="NBO")
        self.prop_b = Property.objects.create(landlord=self.landlord_b, name="B", location="MSA")

    def test_landlord_b_cannot_attach_landlord_as_manager(self):
        self.auth(self.landlord_b)
        response = self.client.patch(
            reverse("properties-detail", kwargs={"pk": self.prop_b.id}),
            {"manager_id": self.manager_of_a.id},
            format="json",
        )
        self.assertIn(response.status_code, (400, 403))
        self.prop_b.refresh_from_db()
        self.assertIsNone(self.prop_b.manager_id)


class PayoutDestinationCooldownTests(_Base):
    """A landlord who just changed their payout destination must wait the
    cool-down window before a payout will release."""

    def setUp(self):
        self.landlord = self.make_user("ll_cooldown", Profile.ROLE_LANDLORD)
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "CD LL",
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0712345678",
            },
        )
        LandlordBalance.objects.create(
            landlord=self.landlord,
            available_balance=Decimal("10000.00"),
            locked_balance=Decimal("0.00"),
        )

    @patch("core.views.execute_intasend_payout")
    @override_settings(LANDLORD_PAYOUT_COOLDOWN_HOURS=24)
    def test_payout_blocked_immediately_after_destination_change(self, mock_execute):
        self.auth(self.landlord)
        # Change the destination via the settings endpoint.
        update = self.client.patch(
            reverse("landlord-settings"),
            {
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0799000000",
            },
            format="json",
        )
        self.assertEqual(update.status_code, 200)

        # Immediately try to pay out — must be blocked by the cool-down.
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "5000.00",
                "method": LandlordPayout.METHOD_MPESA,
                "destination": "0799000000",  # matches the new saved destination
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data.get("code"), "destination_cooldown_active")
        mock_execute.assert_not_called()

    @patch("core.views.execute_intasend_payout")
    @override_settings(LANDLORD_PAYOUT_COOLDOWN_HOURS=24)
    def test_payout_allowed_after_cooldown_expires(self, mock_execute):
        # Settled outcome → 201 PAID; matches the old happy-path expectation
        # while using the new structured response shape.
        mock_execute.return_value = {
            "outcome": "settled",
            "provider_reference": "cooldown-ok",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {"status": "COMPLETED"},
        }
        # Backdate the change time to before the cool-down.
        ls = self.landlord.landlord_settings
        ls.payout_destination_updated_at = timezone.now() - timedelta(hours=48)
        ls.save(update_fields=["payout_destination_updated_at"])

        self.auth(self.landlord)
        response = self.client.post(
            reverse("landlord-payout-request"),
            {
                "amount": "1000.00",
                "method": LandlordPayout.METHOD_MPESA,
                "destination": "0712345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)


class JWTBlacklistTests(_Base):
    def test_logout_blacklists_refresh_token(self):
        user = self.make_user("logout_user", Profile.ROLE_TENANT)
        token_response = self.client.post(
            reverse("token_obtain_pair"),
            {"username": user.username, "password": STRONG_PASSWORD},
            format="json",
        )
        refresh = token_response.data["refresh"]
        access = token_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        logout = self.client.post(reverse("auth-logout"), {"refresh": refresh}, format="json")
        self.assertEqual(logout.status_code, 205)

        # The refresh token should now be unusable.
        self.client.credentials()
        refresh_response = self.client.post(
            reverse("token_refresh"), {"refresh": refresh}, format="json",
        )
        self.assertEqual(refresh_response.status_code, 401)

    def test_logout_requires_authentication(self):
        response = self.client.post(reverse("auth-logout"), {"refresh": "anything"}, format="json")
        self.assertEqual(response.status_code, 401)
