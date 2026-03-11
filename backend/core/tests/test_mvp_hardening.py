from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import Lease, MaintenanceRequest, PaymentTransaction, Profile, Property, TenantInvite, Unit


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

    def test_invite_accept_rejects_existing_username(self):
        existing = self.create_user("existing_user", Profile.ROLE_MANAGER)
        invite = TenantInvite.objects.create(
            full_name="Tenant One",
            invited_by=self.landlord,
            property=self.property,
            unit=self.unit,
            expires_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.post(
            reverse("invites-accept", kwargs={"pk": str(invite.token)}),
            {"username": existing.username, "password": "StrongPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Username already exists", response.data["detail"])


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
