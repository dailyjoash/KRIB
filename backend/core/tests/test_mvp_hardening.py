from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import Document, Lease, MaintenanceRequest, Notification, PaymentTransaction, Profile, Property, Tenant, TenantInvite, Unit, compute_lease_rent_status


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
        self.assertEqual(response.status_code, 403)

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
        response = self.client.get(reverse("users-list"), {"role": Profile.ROLE_MANAGER})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_manager_cannot_reassign_property_manager(self):
        self.auth(self.manager)
        response = self.client.patch(
            reverse("properties-detail", kwargs={"pk": self.property_a.id}),
            {"manager_id": self.manager_b.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

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
        self.manager.is_active = False
        self.manager.save(update_fields=["is_active"])

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

    @patch("core.serializers.build_lease_agreement_pdf")
    def test_lease_create_captures_identity_and_generates_lease_document(self, mock_build_lease_agreement_pdf):
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
                "identity_document": SimpleUploadedFile("passport.jpg", b"image-bytes", content_type="image/jpeg"),
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


@override_settings(
    MPESA_CONSUMER_KEY="key",
    MPESA_CONSUMER_SECRET="secret",
    MPESA_SHORTCODE="174379",
    MPESA_PASSKEY="passkey",
    MPESA_CALLBACK_URL="https://example.com/callback",
)
class PaymentCallbackTests(BaseAPITestCase):
    def setUp(self):
        self.landlord = self.create_user("landlord_pay", Profile.ROLE_LANDLORD)
        self.tenant = self.create_user("tenant_pay", Profile.ROLE_TENANT)
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

    def _callback_payload(self, checkout_id, result_code=0):
        return {
            "Body": {
                "stkCallback": {
                    "CheckoutRequestID": checkout_id,
                    "ResultCode": result_code,
                    "ResultDesc": "OK" if result_code == 0 else "Failed",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "MpesaReceiptNumber", "Value": "RCP123"},
                            {"Name": "TransactionDate", "Value": "20240101120000"},
                        ]
                    },
                }
            }
        }

    @patch("core.views._daraja_stk_push")
    @patch("core.views._missing_daraja_env_vars", return_value=[])
    def test_initiate_and_callback_success_is_idempotent(self, _missing, mock_push):
        mock_push.return_value = {"CheckoutRequestID": "checkout-1", "MerchantRequestID": "merchant-1", "ResponseCode": "0"}
        self.auth(self.tenant)
        initiate = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "10000.00"},
            format="json",
        )
        self.assertEqual(initiate.status_code, 201)

        callback_url = reverse("stk-callback")
        first = self.client.post(callback_url, self._callback_payload("checkout-1", result_code=0), format="json")
        self.assertEqual(first.status_code, 200)

        second = self.client.post(callback_url, self._callback_payload("checkout-1", result_code=0), format="json")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["detail"], "Duplicate callback ignored.")

        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-1")
        self.assertEqual(payment.status, PaymentTransaction.STATUS_SUCCESS)
        self.assertTrue(payment.allocation_done)

    @patch("core.views._daraja_stk_push")
    @patch("core.views._missing_daraja_env_vars", return_value=[])
    def test_callback_failure_marks_failed(self, _missing, mock_push):
        mock_push.return_value = {"CheckoutRequestID": "checkout-2", "MerchantRequestID": "merchant-2", "ResponseCode": "0"}
        self.auth(self.tenant)
        self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "10000.00"},
            format="json",
        )
        response = self.client.post(reverse("stk-callback"), self._callback_payload("checkout-2", result_code=1), format="json")
        self.assertEqual(response.status_code, 200)
        payment = PaymentTransaction.objects.get(checkout_request_id="checkout-2")
        self.assertEqual(payment.status, PaymentTransaction.STATUS_FAILED)

    @patch("core.views._daraja_stk_push")
    @patch("core.views._missing_daraja_env_vars", return_value=[])
    def test_initiate_allows_partial_payment_amount(self, _missing, mock_push):
        mock_push.return_value = {"CheckoutRequestID": "checkout-3", "MerchantRequestID": "merchant-3", "ResponseCode": "0"}
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

    @patch("core.views._daraja_stk_push")
    @patch("core.views._missing_daraja_env_vars", return_value=[])
    def test_initiate_rejects_amount_above_remaining_balance(self, _missing, mock_push):
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

    @patch("core.views._daraja_stk_push")
    @patch("core.views._missing_daraja_env_vars", return_value=[])
    def test_initiate_allows_same_partial_amount_more_than_once(self, _missing, mock_push):
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
        mock_push.return_value = {"CheckoutRequestID": "checkout-4", "MerchantRequestID": "merchant-4", "ResponseCode": "0"}
        self.auth(self.tenant)
        response = self.client.post(
            reverse("stk-initiate"),
            {"lease_id": self.lease.id, "phone_number": "254700000001", "amount": "2500.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

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
        self.assertFalse(PaymentTransaction.objects.filter(tenant=self.tenant).exists())
        self.tenant.profile.refresh_from_db()
        self.assertEqual(self.tenant.profile.wallet_available, Decimal("5000.00"))


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
