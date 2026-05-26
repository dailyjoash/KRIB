import hashlib
import hmac
import json
from io import StringIO
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import Document, LandlordBalance, LandlordPayout, LandlordSettings, Lease, LedgerTransaction, MaintenanceRequest, Notification, PaymentTransaction, Profile, Property, Tenant, TenantInvite, Unit, compute_lease_rent_status
from core.services import can_withdraw_wallet


class BaseAPITestCase(APITestCase):
    def create_user(self, username, role, password="StrongPass123!"):
        user = User.objects.create_user(username=username, password=password)
        profile = user.profile
        profile.role = role
        profile.save(update_fields=["role"])
        return user

    def auth(self, user, password="StrongPass123!"):
        response = self.client.post(reverse("token_obtain_pair"), {"username": user.username, "password": password}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


class RoleScopeTests(BaseAPITestCase):
    def setUp(self):
        self.landlord_a = self.create_user("landlord_a", Profile.ROLE_LANDLORD)
        self.landlord_b = self.create_user("landlord_b", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager", Profile.ROLE_MANAGER)
        self.manager_b = self.create_user("manager_b", Profile.ROLE_MANAGER)
        self.tenant = self.create_user("tenant_scope", Profile.ROLE_TENANT)

        self.property_a = Property.objects.create(landlord=self.landlord_a, manager=self.manager, name="A", location="NBO")
        self.property_b = Property.objects.create(landlord=self.landlord_b, name="B", location="MSA")

    def test_manager_cannot_create_unit_for_unassigned_property(self):
        self.auth(self.manager)
        response = self.client.post(
            reverse("units-list"),
            {
                "property_id": self.property_b.id,
                "unit_number": "B1",
                "unit_type": Unit.TYPE_SINGLE,
                "rent_amount": "10000.00",
                "deposit": "10000.00",
            },
            format="json",
        )
        # 400 = scoped serializer field rejected the FK (security hardening).
        # 403 = view's perform_create rejected the request.
        # Both are acceptable; the critical guarantee is the unit was NOT
        # created in a property the manager does not manage.
        self.assertIn(response.status_code, (400, 403))
        self.assertFalse(Unit.objects.filter(property=self.property_b, unit_number="B1").exists())

    def test_manager_can_create_unit_for_assigned_property(self):
        self.auth(self.manager)
        response = self.client.post(
            reverse("units-list"),
            {
                "property_id": self.property_a.id,
                "unit_number": "A1",
                "unit_type": Unit.TYPE_SINGLE,
                "rent_amount": "10000.00",
                "deposit": "10000.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_tenant_cannot_list_users(self):
        self.auth(self.tenant)
        # Tenants get an empty list for non-self roles; for their own role
        # they see exactly one row (themselves). Either way they MUST NOT see
        # other tenants' or managers' details.
        manager_response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_MANAGER})
        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual(manager_response.data, [])

        self_response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_TENANT})
        self.assertEqual(self_response.status_code, 200)
        self.assertEqual([item["id"] for item in self_response.data], [self.tenant.id])

    def test_manager_cannot_reassign_property_manager(self):
        self.auth(self.manager)
        response = self.client.patch(
            reverse("properties-detail", kwargs={"pk": self.property_a.id}),
            {"manager_id": self.manager_b.id},
            format="json",
        )
        # Either 400 (scoped queryset rejects FK) or 403 (perform_update blocks).
        # Critical assertion: property_a.manager did NOT change.
        self.assertIn(response.status_code, (400, 403))
        self.property_a.refresh_from_db()
        self.assertEqual(self.property_a.manager_id, self.manager.id)

    def test_landlord_unassigning_last_property_deactivates_manager_account(self):
        self.auth(self.landlord_a)
        response = self.client.patch(
            reverse("properties-detail", kwargs={"pk": self.property_a.id}),
            {"manager_id": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertFalse(self.manager.is_active)

        self.client.credentials()
        login = self.client.post(
            reverse("auth-login"),
            {"email": self.manager.username, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 403)
        self.assertEqual(login.data["detail"], "This manager account is inactive until a property is assigned.")

    def test_unassigning_one_of_multiple_properties_keeps_manager_active(self):
        Property.objects.create(landlord=self.landlord_a, manager=self.manager, name="A2", location="KSM")

        self.auth(self.landlord_a)
        response = self.client.patch(
            reverse("properties-detail", kwargs={"pk": self.property_a.id}),
            {"manager_id": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_assigning_property_reactivates_manager_account(self):
        # Cross-landlord poaching is intentionally blocked, so landlord_b must
        # have a legitimate relationship with this manager. We model that by
        # having landlord_b also send a ManagerInvite and marking it accepted,
        # with a matching email that ties the invite to the existing user.
        from core.models import ManagerInvite

        self.manager.email = "manager-shared@example.com"
        self.manager.is_active = False
        self.manager.save(update_fields=["email", "is_active"])

        ManagerInvite.objects.create(
            email=self.manager.email,
            created_by=self.landlord_b,
            expires_at=timezone.now() + timedelta(days=7),
            accepted_at=timezone.now(),
            is_active=False,
        )

        self.auth(self.landlord_b)
        response = self.client.patch(
            reverse("properties-detail", kwargs={"pk": self.property_b.id}),
            {"manager_id": self.manager.id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_landlord_can_list_accepted_invite_tenant_before_first_lease(self):
        invited_user = self.create_user("tenant_prelease", Profile.ROLE_TENANT)
        invited_user.email = "tenant-prelease@example.com"
        invited_user.save(update_fields=["email"])
        tenant_profile, _ = Tenant.objects.get_or_create(user=invited_user)
        tenant_profile.phone = "254700009999"
        tenant_profile.save(update_fields=["phone"])
        TenantInvite.objects.create(
            full_name="Tenant Prelease",
            email="tenant-prelease@example.com",
            phone="254700009999",
            invited_by=self.landlord_a,
            property=self.property_a,
            status=TenantInvite.STATUS_ACCEPTED,
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.auth(self.landlord_a)
        response = self.client.get(reverse("tenants-list"))

        self.assertEqual(response.status_code, 200)
        usernames = [row["user"]["username"] for row in response.data]
        self.assertIn("tenant_prelease", usernames)


class InviteAcceptanceTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord", Profile.ROLE_LANDLORD)
        self.property = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number="U1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )

    def test_invite_accept_requires_first_and_last_name(self):
        invite = TenantInvite.objects.create(
            full_name="Tenant One",
            invited_by=self.landlord,
            property=self.property,
            unit=self.unit,
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {
                "first_name": "Tenant",
                "password": "StrongPass123!",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("last_name", response.data)

    def test_invite_accept_creates_account_without_identity_document(self):
        invite = TenantInvite.objects.create(
            full_name="Tenant Two",
            invited_by=self.landlord,
            property=self.property,
            unit=self.unit,
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {
                "first_name": "Tenant",
                "last_name": "Two",
                "password": "StrongPass123!",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        created_user = User.objects.get(first_name="Tenant", last_name="Two")
        self.assertTrue(created_user.username.startswith("tenanttwo"))
        self.assertFalse(Document.objects.filter(document_type=Document.TYPE_IDENTITY).exists())


class LeaseOnboardingDocumentTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_lease_docs", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager_lease_docs", Profile.ROLE_MANAGER)
        self.tenant = self.create_user("tenant_lease_docs", Profile.ROLE_TENANT)
        # Tie the tenant to this landlord via an accepted TenantInvite so the
        # scoped LeaseSerializer.tenant_id queryset recognizes them as a
        # legitimate target. (Security hardening: a landlord must not be able
        # to graft an unrelated tenant onto a lease.)
        self.tenant.email = "tenant-lease-docs@example.com"
        self.tenant.save(update_fields=["email"])
        TenantInvite.objects.create(
            full_name="Tenant LeaseDocs",
            email=self.tenant.email,
            invited_by=self.landlord,
            status=TenantInvite.STATUS_ACCEPTED,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.property = Property.objects.create(
            landlord=self.landlord,
            manager=self.manager,
            name="Riverside Apartments",
            location="Eldoret",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number="A2",
            unit_type=Unit.TYPE_BEDSITTER,
            rent_amount=Decimal("8000.00"),
            deposit=Decimal("8000.00"),
        )

    @patch("core.serializers.magic")
    @patch("core.serializers.build_lease_agreement_pdf")
    def test_lease_create_captures_identity_and_generates_lease_document(self, mock_build_lease_agreement_pdf, mock_magic):
        mock_magic.from_buffer.return_value = "image/jpeg"
        mock_build_lease_agreement_pdf.return_value = (
            "lease-agreement.pdf",
            SimpleUploadedFile("lease-agreement.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
        )
        self.auth(self.landlord)

        response = self.client.post(
            reverse("leases-list"),
            {
                "unit_id": self.unit.id,
                "tenant_id": self.tenant.id,
                "start_date": timezone.localdate().isoformat(),
                "due_day": 5,
                "status": Lease.STATUS_ACTIVE,
                "rent_amount": "8000.00",
                "identity_document": SimpleUploadedFile(
                    "passport.jpg",
                    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9",
                    content_type="image/jpeg",
                ),
                "tenant_signature": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9VEWil8AAAAASUVORK5CYII=",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        lease = Lease.objects.get()
        identity_document = Document.objects.get(document_type=Document.TYPE_IDENTITY, lease=lease)
        lease_document = Document.objects.get(document_type=Document.TYPE_LEASE, lease=lease)
        self.assertEqual(identity_document.tenant_id, self.tenant.id)
        self.assertEqual(lease_document.tenant_id, self.tenant.id)
        self.assertEqual(identity_document.uploaded_by_id, self.landlord.id)
        self.assertEqual(lease_document.uploaded_by_id, self.landlord.id)

    def test_lease_create_requires_identity_document_and_signature(self):
        self.auth(self.landlord)

        response = self.client.post(
            reverse("leases-list"),
            {
                "unit_id": self.unit.id,
                "tenant_id": self.tenant.id,
                "start_date": timezone.localdate().isoformat(),
                "due_day": 5,
                "status": Lease.STATUS_ACTIVE,
                "rent_amount": "8000.00",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("identity_document", response.data)
        self.assertIn("tenant_signature", response.data)

    @patch("core.views.send_sms", return_value=True)
    @patch("core.views.send_mail")
    def test_landlord_can_remove_tenant_by_ending_active_lease(self, mock_send_mail, mock_send_sms):
        self.tenant.email = "tenant-remove@example.com"
        self.tenant.save(update_fields=["email"])
        tenant_profile = self.tenant.profile
        tenant_profile.phone_number = "254700000099"
        tenant_profile.save(update_fields=["phone_number"])
        lease = Lease.objects.create(
            unit=self.unit,
            tenant=self.tenant,
            rent_amount=Decimal("8000.00"),
            start_date=timezone.localdate(),
            due_day=5,
            status=Lease.STATUS_ACTIVE,
        )
        self.auth(self.landlord)

        response = self.client.post(reverse("leases-remove-tenant", kwargs={"pk": lease.id}))

        self.assertEqual(response.status_code, 200)
        lease.refresh_from_db()
        self.unit.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_INACTIVE)
        self.assertEqual(lease.end_date, timezone.localdate())
        self.assertEqual(self.unit.status, Unit.STATUS_VACANT)
        mock_send_mail.assert_called_once()
        mock_send_sms.assert_called_once()

    def test_manager_can_remove_tenant_for_assigned_property(self):
        lease = Lease.objects.create(
            unit=self.unit,
            tenant=self.tenant,
            rent_amount=Decimal("8000.00"),
            start_date=timezone.localdate(),
            due_day=5,
            status=Lease.STATUS_ACTIVE,
        )
        self.auth(self.manager)

        response = self.client.post(reverse("leases-remove-tenant", kwargs={"pk": lease.id}))

        self.assertEqual(response.status_code, 200)
        lease.refresh_from_db()
        self.assertEqual(lease.status, Lease.STATUS_INACTIVE)


@override_settings(
    FRONTEND_URL="http://localhost:5173",
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.com",
    DEFAULT_FROM_EMAIL="no-reply@krib.local",
)
class InviteDeliveryTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_invites", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager_invites", Profile.ROLE_MANAGER)
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Test Properties",
                "payout_method": "MPESA",
                "payout_destination": "+254700000001",
            },
        )
        self.property = Property.objects.create(
            landlord=self.landlord,
            manager=self.manager,
            name="Riverside Apartments",
            location="Eldoret",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number="A1",
            unit_type=Unit.TYPE_BEDSITTER,
            rent_amount=Decimal("8000.00"),
            deposit=Decimal("8000.00"),
        )

    @patch("core.views.send_sms", return_value=True)
    @patch("core.views.send_mail")
    def test_landlord_manager_invite_returns_frontend_link_and_triggers_delivery(self, mock_send_mail, mock_send_sms):
        self.auth(self.landlord)
        response = self.client.post(
            reverse("manager-invite-create"),
            {"name": "Joash", "email": "joash@example.com", "phone": "254700000001"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["invite_link"].startswith("http://localhost:5173/invite/manager/"))
        self.assertTrue(response.data["email_sent"])
        self.assertTrue(response.data["sms_sent"])
        mock_send_mail.assert_called_once()
        mock_send_sms.assert_called_once()

    @patch("core.views.send_sms", return_value=True)
    @patch("core.views.send_mail")
    def test_tenant_invite_returns_frontend_link_and_triggers_delivery(self, mock_send_mail, mock_send_sms):
        self.auth(self.landlord)
        response = self.client.post(
            reverse("invites-list"),
            {
                "full_name": "Tenant One",
                "email": "tenant@example.com",
                "phone": "254700000002",
                "property": self.property.id,
                "unit": self.unit.id,
                "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["invite_link"].startswith("http://localhost:5173/invite/tenant/"))
        self.assertTrue(response.data["email_sent"])
        self.assertTrue(response.data["sms_sent"])
        mock_send_mail.assert_called_once()
        mock_send_sms.assert_called_once()

    def test_tenant_invite_requires_email_or_phone(self):
        self.auth(self.landlord)
        response = self.client.post(
            reverse("invites-list"),
            {
                "full_name": "Tenant One",
                "property": self.property.id,
                "unit": self.unit.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_public_tenant_invite_lookup_uses_token_and_updates_expired_status(self):
        active_invite = TenantInvite.objects.create(
            full_name="Tenant Active",
            email="tenant-active@example.com",
            invited_by=self.landlord,
            property=self.property,
            unit=self.unit,
            expires_at=timezone.now() + timedelta(days=7),
        )
        expired_invite = TenantInvite.objects.create(
            full_name="Tenant Expired",
            email="tenant-expired@example.com",
            invited_by=self.landlord,
            property=self.property,
            unit=self.unit,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        active_response = self.client.get(reverse("invites-detail", args=[active_invite.token]))
        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(active_response.data["token"], str(active_invite.token))
        self.assertEqual(active_response.data["status"], TenantInvite.STATUS_PENDING)

        expired_response = self.client.get(reverse("invites-detail", args=[expired_invite.token]))
        self.assertEqual(expired_response.status_code, 200)
        self.assertEqual(expired_response.data["status"], TenantInvite.STATUS_EXPIRED)
        expired_invite.refresh_from_db()
        self.assertEqual(expired_invite.status, TenantInvite.STATUS_EXPIRED)

    @patch("core.views.send_sms", return_value=True)
    @patch("core.views.send_mail")
    def test_tenant_invite_can_be_resent_and_cancelled(self, mock_send_mail, mock_send_sms):
        invite = TenantInvite.objects.create(
            full_name="Tenant Resend",
            email="tenant@example.com",
            phone="254700000002",
            invited_by=self.landlord,
            property=self.property,
            unit=self.unit,
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.auth(self.landlord)
        resend = self.client.post(reverse("invites-resend", args=[invite.id]), format="json")
        self.assertEqual(resend.status_code, 200)
        self.assertTrue(resend.data["email_sent"])
        self.assertTrue(resend.data["sms_sent"])

        cancel = self.client.post(reverse("invites-cancel", args=[invite.id]), format="json")
        self.assertEqual(cancel.status_code, 200)
        invite.refresh_from_db()
        self.assertEqual(invite.status, TenantInvite.STATUS_CANCELLED)


@patch.dict(
    "os.environ",
    {
        "INTASEND_API_TOKEN": "token",
        "INTASEND_PUBLISHABLE_KEY": "publishable",
        "INTASEND_TEST_MODE": "true",
        "INTASEND_WEBHOOK_SECRET": "test-secret",
    },
    clear=False,
)
class PaymentCallbackTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_pay", Profile.ROLE_LANDLORD)
        self.tenant = self.create_user("tenant_pay", Profile.ROLE_TENANT)
        self.webhook_secret = "test-secret"
        prop = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        unit = Unit.objects.create(
            property=prop,
            unit_number="U1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )
        self.lease = Lease.objects.create(
            unit=unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )

    def _callback_payload(self, checkout_id, state="COMPLETE"):
        return {
            "invoice_id": checkout_id,
            "state": state,
            "invoice": {
                "invoice_id": checkout_id,
                "mpesa_receipt": "RCP123",
                "value": "10000.00",
                "account": f"LEASE-{self.lease.id}",
            },
        }

    def _signed_callback(self, checkout_id, state="COMPLETE"):
        payload = self._callback_payload(checkout_id, state=state)
        body = json.dumps(payload)
        signature = hmac.new(self.webhook_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        return body, signature

    @patch("core.views.intasend_stk_push")
    def test_initiate_and_callback_success_is_idempotent(self, mock_push):
        mock_push.return_value = {"success": True, "invoice_id": "checkout-1"}
        self.auth(self.tenant)
        initiate = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "10000.00"},
            format="json",
        )
        self.assertEqual(initiate.status_code, 201)

        callback_url = reverse("stk-callback")
        first_body, first_signature = self._signed_callback("checkout-1", state="COMPLETE")
        first = self.client.post(callback_url, data=first_body, content_type="application/json", HTTP_X_INTASEND_SIGNATURE=first_signature)
        self.assertEqual(first.status_code, 200)

        second_body, second_signature = self._signed_callback("checkout-1", state="COMPLETE")
        second = self.client.post(callback_url, data=second_body, content_type="application/json", HTTP_X_INTASEND_SIGNATURE=second_signature)
        self.assertEqual(second.status_code, 200)
        # The new provider-agnostic core uses the wording "Duplicate event
        # ignored."; the old IntaSend-specific wording was "Duplicate callback
        # ignored." — both indicate the same idempotent short-circuit.
        self.assertIn(second.data["detail"], ("Duplicate event ignored.", "Duplicate callback ignored."))

        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-1")
        self.assertEqual(payment.status, PaymentTransaction.STATUS_SUCCESS)
        self.assertTrue(payment.allocation_done)

    @patch("core.views.intasend_stk_push")
    def test_callback_failure_marks_failed(self, mock_push):
        mock_push.return_value = {"success": True, "invoice_id": "checkout-2"}
        self.auth(self.tenant)
        self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "10000.00"},
            format="json",
        )
        body, signature = self._signed_callback("checkout-2", state="FAILED")
        response = self.client.post(reverse("stk-callback"), data=body, content_type="application/json", HTTP_X_INTASEND_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-2")
        self.assertEqual(payment.status, PaymentTransaction.STATUS_FAILED)

    @patch("core.views.intasend_stk_push")
    def test_initiate_allows_partial_payment_amount(self, mock_push):
        mock_push.return_value = {"success": True, "invoice_id": "checkout-3"}
        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "2500.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-3")
        self.assertEqual(payment.amount, Decimal("2500.00"))
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)

    @patch("core.views.intasend_stk_push")
    def test_initiate_normalizes_local_phone_number(self, mock_push):
        mock_push.return_value = {"success": True, "invoice_id": "checkout-local"}
        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "0712 345 678", "amount": "2500.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-local")
        self.assertEqual(payment.phone_number, "254712345678")
        mock_push.assert_called_once_with("254712345678", payment.amount, f"LEASE-{self.lease.id}")

    def test_initiate_rejects_invalid_phone_number(self):
        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "12345", "amount": "2500.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid Kenyan M-Pesa number", response.data["phone_number"][0])

    @patch("core.views.intasend_stk_push")
    def test_initiate_rejects_amount_above_remaining_balance(self, mock_push):
        PaymentTransaction.objects.create(
            lease=self.lease,
            tenant=self.tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            billing_period=timezone.localdate().replace(day=1),
            phone_number="254700000001",
            amount=Decimal("4000.00"),
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id="existing-success",
            status=PaymentTransaction.STATUS_SUCCESS,
            allocation_done=True,
        )

        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "7000.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("remaining balance", response.data["detail"])

    @patch("core.views.intasend_stk_push")
    def test_initiate_allows_same_partial_amount_more_than_once(self, mock_push):
        PaymentTransaction.objects.create(
            lease=self.lease,
            tenant=self.tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            billing_period=timezone.localdate().replace(day=1),
            phone_number="254700000001",
            amount=Decimal("2500.00"),
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id="existing-success-2500",
            status=PaymentTransaction.STATUS_SUCCESS,
            allocation_done=True,
        )
        mock_push.return_value = {"success": True, "invoice_id": "checkout-4"}
        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "2500.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    @patch("core.views.intasend_stk_push")
    def test_initiate_applies_wallet_credit_before_partial_stk_push(self, mock_push):
        self.tenant.profile.wallet_available = Decimal("5000.00")
        self.tenant.profile.save(update_fields=["wallet_available"])
        mock_push.return_value = {"success": True, "invoice_id": "checkout-wallet-partial"}

        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "10000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-wallet-partial")
        self.assertEqual(payment.amount, Decimal("5000.00"))
        mock_push.assert_called_once_with("254700000001", Decimal("5000.00"), f"LEASE-{self.lease.id}")
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("0.00"))
        self.assertTrue(
            PaymentTransaction.objects.filter(
                lease=self.lease,
                tenant=self.tenant,
                amount=Decimal("5000.00"),
                status=PaymentTransaction.STATUS_SUCCESS,
                result_desc="Auto wallet rent debit",
            ).exists()
        )

    @patch("core.views.intasend_stk_push")
    def test_initiate_skips_stk_when_wallet_fully_covers_rent(self, mock_push):
        self.tenant.profile.wallet_available = Decimal("10000.00")
        self.tenant.profile.save(update_fields=["wallet_available"])

        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "10000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Rent was fully covered by wallet credit.")
        mock_push.assert_not_called()
        self.assertFalse(
            PaymentTransaction.objects.filter(
                lease=self.lease,
                tenant=self.tenant,
                payment_method=PaymentTransaction.METHOD_MPESA,
                status=PaymentTransaction.STATUS_PENDING,
            ).exists()
        )
        self.assertTrue(
            PaymentTransaction.objects.filter(
                lease=self.lease,
                tenant=self.tenant,
                amount=Decimal("10000.00"),
                status=PaymentTransaction.STATUS_SUCCESS,
                allocation_done=True,
                result_desc="Auto wallet rent debit",
            ).exists()
        )

    def test_callback_invalid_signature_does_not_process_payment(self):
        payment = PaymentTransaction.objects.create(
            lease=self.lease,
            tenant=self.tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            billing_period=timezone.localdate().replace(day=1),
            phone_number="254700000001",
            amount=Decimal("10000.00"),
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id="checkout-invalid-signature",
            status=PaymentTransaction.STATUS_PENDING,
        )

        body = json.dumps(self._callback_payload("checkout-invalid-signature", state="COMPLETE"))
        response = self.client.post(
            reverse("stk-callback"),
            data=body,
            content_type="application/json",
            HTTP_X_INTASEND_SIGNATURE="bad-signature",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid signature.")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentTransaction.STATUS_PENDING)


class LandlordPayoutRequestTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_payout", Profile.ROLE_LANDLORD)
        self.tenant = self.create_user("tenant_payout", Profile.ROLE_TENANT)
        self.balance = LandlordBalance.objects.create(
            landlord=self.landlord,
            available_balance=Decimal("15000.00"),
            locked_balance=Decimal("0.00"),
        )
        # Payouts now require a verified destination saved in LandlordSettings
        # (security hardening). The legacy tests assumed any destination would
        # be accepted, so register the canonical destination here.
        LandlordSettings.objects.update_or_create(
            user=self.landlord,
            defaults={
                "business_name": "Payout LL",
                "payout_method": LandlordPayout.METHOD_MPESA,
                "payout_destination": "0712345678",
            },
        )
        self.property = Property.objects.create(
            landlord=self.landlord,
            name="Test Property",
            location="Nairobi",
        )
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number="A1",
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )
        self.lease = Lease.objects.create(
            unit=self.unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate().replace(day=1),
            status=Lease.STATUS_ACTIVE,
            due_day=1,
        )

    @patch("core.views.execute_intasend_payout")
    def test_payout_provider_settled_marks_paid_and_reduces_balance(self, mock_execute):
        # New lifecycle: only an explicit "settled" provider outcome moves
        # the payout straight to PAID. Provider "accepted" goes to
        # PROCESSING and is exercised in test_payout_lifecycle.py.
        mock_execute.return_value = {
            "outcome": "settled",
            "provider_reference": "track-paid-1",
            "provider_status": "COMPLETED",
            "detail": None,
            "redacted_response": {"status": "COMPLETED", "tracking_id": "track-paid-1"},
        }
        self.auth(self.landlord)

        response = self.client.post(
            reverse("landlord-payout-request"),
            {"amount": "5000.00", "method": LandlordPayout.METHOD_MPESA, "destination": "0712345678"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_PAID)
        self.assertIsNotNone(payout.paid_at)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_balance, Decimal("10000.00"))
        self.assertEqual(
            LedgerTransaction.objects.filter(
                user=self.landlord,
                kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
                status=LedgerTransaction.STATUS_PAID,
            ).count(),
            1,
        )

    @patch("core.views.execute_intasend_payout")
    def test_payout_provider_rejected_restores_balance_and_marks_failed(self, mock_execute):
        mock_execute.return_value = {
            "outcome": "rejected",
            "provider_reference": None,
            "provider_status": "FAILED",
            "detail": "Provider unavailable",
            "redacted_response": {"status": "FAILED"},
        }
        self.auth(self.landlord)

        response = self.client.post(
            reverse("landlord-payout-request"),
            {"amount": "5000.00", "method": LandlordPayout.METHOD_MPESA, "destination": "0712345678"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)
        payout = LandlordPayout.objects.get(landlord=self.landlord)
        self.assertEqual(payout.status, LandlordPayout.STATUS_FAILED)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.available_balance, Decimal("15000.00"))
        request_ledger = LedgerTransaction.objects.get(
            user=self.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
        )
        self.assertEqual(request_ledger.status, LedgerTransaction.STATUS_REJECTED)

    def test_bank_payout_requires_bank_code(self):
        self.auth(self.landlord)

        response = self.client.post(
            reverse("landlord-payout-request"),
            {"amount": "5000.00", "method": LandlordPayout.METHOD_BANK, "destination": "0123456789"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("bank_code", response.data)

    def test_dashboard_summary_carries_forward_previous_month_arrears(self):
        previous_month = (timezone.localdate().replace(day=1) - timedelta(days=1)).replace(day=1)
        self.lease.start_date = previous_month
        self.lease.save(update_fields=["start_date"])

        self.auth(self.tenant)
        response = self.client.get(reverse("dashboard-summary"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["rent"]["balance"]), Decimal("20000.00"))
        self.assertEqual(response.data["rent"]["status"], "OVERDUE")
        self.assertEqual(Decimal(response.data["rent"]["carried_forward_balance"]), Decimal("10000.00"))

    def test_compute_rent_status_allocates_payments_to_oldest_arrears_first(self):
        previous_month = (timezone.localdate().replace(day=1) - timedelta(days=1)).replace(day=1)
        self.lease.start_date = previous_month
        self.lease.save(update_fields=["start_date"])
        current_period = timezone.localdate().strftime("%Y-%m")

        PaymentTransaction.objects.create(
            lease=self.lease,
            tenant=self.tenant,
            period=current_period,
            billing_period=timezone.localdate().replace(day=1),
            phone_number="254700000001",
            amount=Decimal("12000.00"),
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id="carry-forward-payment",
            status=PaymentTransaction.STATUS_SUCCESS,
            allocation_done=True,
        )

        rent = compute_lease_rent_status(self.lease, period=current_period, today=timezone.localdate().replace(day=1))
        self.assertEqual(rent["status"], "PARTIAL")
        self.assertEqual(rent["balance"], Decimal("8000.00"))
        self.assertEqual(rent["carried_forward_balance"], Decimal("0.00"))


class MaintenanceScopeTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_m", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager_m", Profile.ROLE_MANAGER)
        self.tenant = self.create_user("tenant_m", Profile.ROLE_TENANT)
        self.other_tenant = self.create_user("tenant_x", Profile.ROLE_TENANT)

        prop = Property.objects.create(landlord=self.landlord, manager=self.manager, name="P", location="NBO")
        unit = Unit.objects.create(
            property=prop,
            unit_number="U1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )
        self.lease = Lease.objects.create(
            unit=unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        self.request_obj = MaintenanceRequest.objects.create(tenant=self.tenant, lease=self.lease, issue="Leak")

    def test_tenant_cannot_create_maintenance_for_other_lease(self):
        self.auth(self.other_tenant)
        response = self.client.post(reverse("maintenance-list"), {"lease_id": self.lease.id, "issue": "Bad"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_manager_can_only_see_scoped_maintenance(self):
        self.auth(self.manager)
        response = self.client.get(reverse("maintenance-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.request_obj.id)

    def test_tenant_cannot_update_maintenance_status(self):
        self.auth(self.tenant)
        response = self.client.patch(reverse("maintenance-detail", kwargs={"pk": self.request_obj.id}), {"status": "resolved"}, format="json")
        self.assertEqual(response.status_code, 403)


class DashboardSummaryTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_summary", Profile.ROLE_LANDLORD)
        self.tenant = self.create_user("tenant_summary", Profile.ROLE_TENANT)
        prop = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        unit = Unit.objects.create(
            property=prop,
            unit_number="U1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )
        self.lease = Lease.objects.create(
            unit=unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        self.tenant.profile.wallet_available = Decimal("5000.00")
        self.tenant.profile.save(update_fields=["wallet_available"])

    def test_summary_get_does_not_create_wallet_payment(self):
        self.auth(self.tenant)
        response = self.client.get(reverse("dashboard-summary"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data["rent"]["balance"]), Decimal("5000.00"))
        self.assertEqual(Decimal(response.data["active_lease"]["rent_status"]["balance"]), Decimal("5000.00"))
        self.assertFalse(PaymentTransaction.objects.filter(tenant=self.tenant).exists())
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("5000.00"))


class WalletWithdrawalTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_wallet", Profile.ROLE_LANDLORD)
        self.tenant = self.create_user("tenant_wallet", Profile.ROLE_TENANT)
        self.tenant.profile.wallet_available = Decimal("5000.00")
        self.tenant.profile.save(update_fields=["wallet_available"])

    def test_can_withdraw_wallet_allows_tenant_with_no_active_leases(self):
        allowed, message = can_withdraw_wallet(self.tenant, Decimal("1000.00"))
        self.assertTrue(allowed)
        self.assertIsNone(message)

    def test_can_withdraw_wallet_blocks_if_any_active_lease_has_arrears(self):
        property_one = Property.objects.create(landlord=self.landlord, name="One", location="NBO")
        property_two = Property.objects.create(landlord=self.landlord, name="Two", location="KSM")
        unit_one = Unit.objects.create(
            property=property_one,
            unit_number="A1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("6000.00"),
            deposit=Decimal("6000.00"),
        )
        unit_two = Unit.objects.create(
            property=property_two,
            unit_number="B1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("4000.00"),
            deposit=Decimal("4000.00"),
        )
        Lease.objects.create(
            unit=unit_one,
            tenant=self.tenant,
            rent_amount=Decimal("6000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        paid_lease = Lease.objects.create(
            unit=unit_two,
            tenant=self.tenant,
            rent_amount=Decimal("4000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        PaymentTransaction.objects.create(
            lease=paid_lease,
            tenant=self.tenant,
            period=timezone.localdate().strftime("%Y-%m"),
            billing_period=timezone.localdate().replace(day=1),
            phone_number="254700000001",
            amount=Decimal("4000.00"),
            payment_method=PaymentTransaction.METHOD_MPESA,
            checkout_request_id="paid-lease",
            status=PaymentTransaction.STATUS_SUCCESS,
            allocation_done=True,
        )

        allowed, message = can_withdraw_wallet(self.tenant, Decimal("1000.00"))

        self.assertFalse(allowed)
        self.assertIn("outstanding rent", message)

    def test_wallet_withdraw_blocks_before_deducting_balance_when_rent_is_outstanding(self):
        property_obj = Property.objects.create(landlord=self.landlord, name="P", location="NBO")
        unit = Unit.objects.create(
            property=property_obj,
            unit_number="U1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )
        Lease.objects.create(
            unit=unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )

        self.auth(self.tenant)
        response = self.client.post(
            reverse("wallet-withdraw"),
            {"amount": "1000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("outstanding rent", response.data["detail"])
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("5000.00"))
        self.assertFalse(
            LedgerTransaction.objects.filter(
                user=self.tenant,
                kind=LedgerTransaction.KIND_WALLET_WITHDRAW_REQUEST,
            ).exists()
        )

    def test_wallet_withdraw_allows_tenant_without_active_lease(self):
        self.auth(self.tenant)
        response = self.client.post(
            reverse("wallet-withdraw"),
            {"amount": "1000.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("4000.00"))
        self.assertTrue(
            LedgerTransaction.objects.filter(
                user=self.tenant,
                kind=LedgerTransaction.KIND_WALLET_WITHDRAW_REQUEST,
                amount=Decimal("1000.00"),
                status=LedgerTransaction.STATUS_PENDING,
            ).exists()
        )


class UnlockBalancesCommandTests(BaseAPITestCase):
    def test_command_unlocks_due_landlord_credit(self):
        landlord = self.create_user("landlord_unlock", Profile.ROLE_LANDLORD)
        balance = LandlordBalance.objects.create(
            landlord=landlord,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("2500.00"),
        )
        row = LedgerTransaction.objects.create(
            user=landlord,
            kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
            amount=Decimal("2500.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() - timedelta(minutes=5),
            reference_text="rent credit ready",
        )

        stdout = StringIO()
        call_command("unlock_balances", stdout=stdout)

        row.refresh_from_db()
        balance.refresh_from_db()
        self.assertEqual(row.status, LedgerTransaction.STATUS_AVAILABLE)
        self.assertEqual(balance.locked_balance, Decimal("0.00"))
        self.assertEqual(balance.available_balance, Decimal("3500.00"))
        self.assertIn("Unlocked: 1", stdout.getvalue())

    def test_command_unlocks_due_wallet_credit_only(self):
        tenant = self.create_user("tenant_unlock", Profile.ROLE_TENANT)
        profile = tenant.profile
        profile.wallet_available = Decimal("100.00")
        profile.wallet_locked = Decimal("1300.00")
        profile.save(update_fields=["wallet_available", "wallet_locked"])
        due_row = LedgerTransaction.objects.create(
            user=tenant,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            amount=Decimal("900.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() - timedelta(minutes=5),
            reference_text="due wallet credit",
        )
        future_row = LedgerTransaction.objects.create(
            user=tenant,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            amount=Decimal("400.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() + timedelta(hours=2),
            reference_text="future wallet credit",
        )

        call_command("unlock_balances")

        profile.refresh_from_db()
        due_row.refresh_from_db()
        future_row.refresh_from_db()
        self.assertEqual(due_row.status, LedgerTransaction.STATUS_AVAILABLE)
        self.assertEqual(future_row.status, LedgerTransaction.STATUS_LOCKED)
        self.assertEqual(profile.wallet_available, Decimal("1000.00"))
        self.assertEqual(profile.wallet_locked, Decimal("400.00"))

    def test_command_continues_when_one_unlock_fails(self):
        bad_tenant = self.create_user("tenant_unlock_bad", Profile.ROLE_TENANT)
        good_tenant = self.create_user("tenant_unlock_good", Profile.ROLE_TENANT)

        bad_profile = bad_tenant.profile
        bad_profile.wallet_available = Decimal("0.00")
        bad_profile.wallet_locked = Decimal("500.00")
        bad_profile.save(update_fields=["wallet_available", "wallet_locked"])
        good_profile = good_tenant.profile
        good_profile.wallet_available = Decimal("200.00")
        good_profile.wallet_locked = Decimal("700.00")
        good_profile.save(update_fields=["wallet_available", "wallet_locked"])

        bad_row = LedgerTransaction.objects.create(
            user=bad_tenant,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            amount=Decimal("500.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() - timedelta(minutes=5),
            reference_text="bad wallet credit",
        )
        good_row = LedgerTransaction.objects.create(
            user=good_tenant,
            kind=LedgerTransaction.KIND_WALLET_CREDIT,
            amount=Decimal("700.00"),
            status=LedgerTransaction.STATUS_LOCKED,
            available_at=timezone.now() - timedelta(minutes=5),
            reference_text="good wallet credit",
        )

        original_save = Profile.save

        def flaky_save(profile_self, *args, **kwargs):
            if profile_self.pk == bad_profile.pk:
                raise RuntimeError("simulated unlock failure")
            return original_save(profile_self, *args, **kwargs)

        stdout = StringIO()
        # The unlock command was refactored to delegate to
        # `core.services._unlock_single_ledger_row` which imports Profile
        # locally. Patch the class on its defining module so the lookup
        # inside the service sees the flaky save.
        with patch("core.models.Profile.save", new=flaky_save):
            call_command("unlock_balances", stdout=stdout)

        bad_profile.refresh_from_db()
        good_profile.refresh_from_db()
        bad_row.refresh_from_db()
        good_row.refresh_from_db()

        self.assertEqual(bad_row.status, LedgerTransaction.STATUS_LOCKED)
        self.assertEqual(bad_profile.wallet_available, Decimal("0.00"))
        self.assertEqual(bad_profile.wallet_locked, Decimal("500.00"))
        self.assertEqual(good_row.status, LedgerTransaction.STATUS_AVAILABLE)
        self.assertEqual(good_profile.wallet_available, Decimal("900.00"))
        self.assertEqual(good_profile.wallet_locked, Decimal("0.00"))
        self.assertIn("Unlocked: 1", stdout.getvalue())
        self.assertIn("Failed: 1", stdout.getvalue())


class DocumentAccessTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_docs", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager_docs", Profile.ROLE_MANAGER)
        self.tenant = self.create_user("tenant_docs", Profile.ROLE_TENANT)
        self.other_tenant = self.create_user("tenant_other_docs", Profile.ROLE_TENANT)
        self.property = Property.objects.create(landlord=self.landlord, manager=self.manager, name="P", location="NBO")
        unit = Unit.objects.create(
            property=self.property,
            unit_number="U1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("10000.00"),
            deposit=Decimal("10000.00"),
        )
        lease = Lease.objects.create(
            unit=unit,
            tenant=self.tenant,
            rent_amount=Decimal("10000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        self.document = Document.objects.create(
            property=self.property,
            lease=lease,
            uploaded_by=self.landlord,
            document_type=Document.TYPE_LEASE,
            file_path=SimpleUploadedFile("lease.pdf", b"pdf-content", content_type="application/pdf"),
        )
        self.identity_document = Document.objects.create(
            property=self.property,
            tenant=self.tenant,
            uploaded_by=self.tenant,
            document_type=Document.TYPE_IDENTITY,
            file_path=SimpleUploadedFile("passport.jpg", b"img-content", content_type="image/jpeg"),
        )
        self.other_identity_document = Document.objects.create(
            property=self.property,
            tenant=self.other_tenant,
            uploaded_by=self.other_tenant,
            document_type=Document.TYPE_IDENTITY,
            file_path=SimpleUploadedFile("other-passport.jpg", b"other-img", content_type="image/jpeg"),
        )

    def test_manager_can_list_documents_for_managed_property(self):
        self.auth(self.manager)
        response = self.client.get(reverse("documents-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)
        tenant_names = {row["tenant_name"] for row in response.data if row["document_type"] == Document.TYPE_IDENTITY}
        self.assertEqual(tenant_names, {self.tenant.username, self.other_tenant.username})

    def test_tenant_cannot_list_other_tenants_identity_documents(self):
        self.auth(self.tenant)
        response = self.client.get(reverse("documents-list"))
        self.assertEqual(response.status_code, 200)
        tenant_names = {row.get("tenant_name") for row in response.data if row["document_type"] == Document.TYPE_IDENTITY}
        self.assertEqual(tenant_names, {self.tenant.username})


class NotificationAndHealthTests(BaseAPITestCase):
    def setUp(self):
        self.user = self.create_user("notice_user", Profile.ROLE_TENANT)
        Notification.objects.create(user=self.user, title="One", message="First")
        Notification.objects.create(user=self.user, title="Two", message="Second")

    def test_health_endpoint_is_public(self):
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")

    def test_mark_all_read_marks_user_notifications(self):
        self.auth(self.user)
        response = self.client.post(reverse("notifications-mark-all-read"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notification.objects.filter(user=self.user, is_read=False).exists())

    def test_clear_read_removes_only_read_notifications(self):
        self.auth(self.user)
        Notification.objects.filter(user=self.user, title="One").update(is_read=True)
        response = self.client.delete(reverse("notifications-clear-read"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Notification.objects.get(user=self.user).title, "Two")


class NotificationComposerTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_notice", Profile.ROLE_LANDLORD)
        self.other_landlord = self.create_user("landlord_other", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager_notice", Profile.ROLE_MANAGER)
        self.tenant = self.create_user("tenant_notice", Profile.ROLE_TENANT)
        self.other_tenant = self.create_user("tenant_elsewhere", Profile.ROLE_TENANT)
        self.tenant.profile.phone_number = "254700000123"
        self.tenant.profile.save(update_fields=["phone_number"])

        property_a = Property.objects.create(landlord=self.landlord, manager=self.manager, name="Alpha", location="Nairobi")
        property_b = Property.objects.create(landlord=self.other_landlord, name="Beta", location="Nakuru")
        unit_a = Unit.objects.create(
            property=property_a,
            unit_number="A1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("12000.00"),
            deposit=Decimal("12000.00"),
        )
        unit_b = Unit.objects.create(
            property=property_b,
            unit_number="B1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("9000.00"),
            deposit=Decimal("9000.00"),
        )
        Lease.objects.create(
            unit=unit_a,
            tenant=self.tenant,
            rent_amount=Decimal("12000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )
        Lease.objects.create(
            unit=unit_b,
            tenant=self.other_tenant,
            rent_amount=Decimal("9000.00"),
            start_date=timezone.localdate(),
            due_day=15,
            status=Lease.STATUS_ACTIVE,
        )

    def test_landlord_can_send_notification_to_scoped_portfolio_users(self):
        self.auth(self.landlord)
        response = self.client.post(
            reverse("notifications-send"),
            {"title": "Inspection notice", "message": "Caretaker visit tomorrow morning.", "audience": "everyone"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(Notification.objects.filter(user=self.tenant, title="Inspection notice").exists())
        self.assertTrue(Notification.objects.filter(user=self.manager, title="Inspection notice").exists())
        self.assertFalse(Notification.objects.filter(user=self.other_tenant, title="Inspection notice").exists())

    @patch("core.views.send_sms", return_value=True)
    def test_manager_can_send_notification_to_scoped_tenants_by_sms(self, mock_send_sms):
        self.auth(self.manager)
        response = self.client.post(
            reverse("notifications-send"),
            {
                "title": "Maintenance",
                "message": "Water outage this evening.",
                "audience": "tenants",
                "send_in_app": True,
                "send_sms": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["delivery"]["in_app"], 1)
        self.assertEqual(response.data["delivery"]["sms"], 1)
        self.assertTrue(Notification.objects.filter(user=self.tenant, title="Maintenance").exists())
        mock_send_sms.assert_called_once()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
    )
    @patch("core.views.send_mail")
    def test_landlord_notification_can_fan_out_email_and_in_app(self, mock_send_mail):
        self.tenant.email = "tenant_notice@example.com"
        self.tenant.save(update_fields=["email"])
        self.auth(self.landlord)
        response = self.client.post(
            reverse("notifications-send"),
            {
                "title": "Lease update",
                "message": "Please review the latest notice.",
                "audience": "tenants",
                "send_in_app": True,
                "send_email": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["delivery"]["in_app"], 1)
        self.assertEqual(response.data["delivery"]["email"], 1)
        mock_send_mail.assert_called_once()


class LeaseTenantContactTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_contact", Profile.ROLE_LANDLORD)
        self.manager = self.create_user("manager_contact", Profile.ROLE_MANAGER)
        self.tenant = self.create_user("tenant_contact", Profile.ROLE_TENANT)
        self.tenant.email = "tenant@example.com"
        self.tenant.save(update_fields=["email"])
        self.tenant.profile.phone_number = "254700000321"
        self.tenant.profile.save(update_fields=["phone_number"])

        self.property = Property.objects.create(landlord=self.landlord, manager=self.manager, name="Gamma", location="Eldoret")
        self.unit = Unit.objects.create(
            property=self.property,
            unit_number="G1",
            unit_type=Unit.TYPE_SINGLE,
            rent_amount=Decimal("8000.00"),
            deposit=Decimal("8000.00"),
        )
        self.lease = Lease.objects.create(
            unit=self.unit,
            tenant=self.tenant,
            rent_amount=Decimal("8000.00"),
            start_date=timezone.localdate(),
            due_day=10,
            status=Lease.STATUS_ACTIVE,
        )

    @patch("core.views.send_sms", return_value=True)
    def test_manager_can_send_sms_to_tenant(self, mock_send_sms):
        self.auth(self.manager)
        response = self.client.post(
            reverse("leases-contact-tenant", args=[self.lease.id]),
            {"channel": "sms", "message": "Please check your rent balance."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "SMS sent to tenant.")
        mock_send_sms.assert_called_once_with("254700000321", "Please check your rent balance.", include_detail=True)
        self.assertTrue(Notification.objects.filter(user=self.tenant, message="Please check your rent balance.").exists())

    @patch("core.views.send_mail")
    def test_landlord_can_send_email_to_tenant(self, mock_send_mail):
        self.auth(self.landlord)
        response = self.client.post(
            reverse("leases-contact-tenant", args=[self.lease.id]),
            {"channel": "email", "subject": "Rent reminder", "message": "Please review your rent statement."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Email sent to tenant.")
        mock_send_mail.assert_called_once()
        self.assertTrue(Notification.objects.filter(user=self.tenant, title="Rent reminder").exists())


class PasswordResetTests(BaseAPITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reset_user",
            email="reset@example.com",
            password="StrongPass123!",
        )

    def test_password_reset_request_and_confirm(self):
        response = self.client.post(reverse("password-reset-request"), {"email": self.user.email}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm = self.client.post(
            reverse("password-reset-confirm"),
            {"uid": uid, "token": token, "new_password": "NewStrongPass123!"},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)

        login = self.client.post(
            reverse("token_obtain_pair"),
            {"username": self.user.username, "password": "NewStrongPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)


class LoginIdentifierTests(BaseAPITestCase):
    def setUp(self):
        self.user = self.create_user("manager_login", Profile.ROLE_MANAGER, password="StrongPass123!")
        self.user.email = ""
        self.user.save(update_fields=["email"])

    def test_login_accepts_username_when_email_is_blank(self):
        response = self.client.post(
            reverse("auth-login"),
            {"email": self.user.username, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], Profile.ROLE_MANAGER)
