from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Property, TenantInvite


class TenantInviteFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.landlord = User.objects.create_user(
            username="landlord",
            email="landlord@example.com",
            password="password123",
            is_staff=True,
        )
        self.property = Property.objects.create(
            title="Sunset Apartments",
            address="Nairobi",
            landlord=self.landlord,
        )

    def test_create_and_accept_invite(self):
        self.client.force_authenticate(user=self.landlord)
        res = self.client.post(
            "/api/invites/",
            {
                "full_name": "Jane Tenant",
                "email": "jane@example.com",
                "property": self.property.id,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        token = res.data["token"]
        self.client.force_authenticate(user=None)
        accept_res = self.client.post(
            f"/api/invites/{token}/accept/",
            {"password": "newpass123"},
            format="json",
        )
        self.assertEqual(accept_res.status_code, 200)
        invite = TenantInvite.objects.get(token=token)
        self.assertEqual(invite.status, TenantInvite.Status.ACCEPTED)

    def test_invite_with_otp_flow(self):
        self.client.force_authenticate(user=self.landlord)
        res = self.client.post(
            "/api/invites/",
            {
                "full_name": "OTP Tenant",
                "email": "otp@example.com",
                "send_otp": True,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        token = res.data["token"]
        invite = TenantInvite.objects.get(token=token)
        self.assertIsNotNone(invite.otp_code)
        self.client.force_authenticate(user=None)
        verify_res = self.client.post(
            f"/api/invites/{token}/verify_otp/",
            {"otp": invite.otp_code},
            format="json",
        )
        self.assertEqual(verify_res.status_code, 200)
        accept_res = self.client.post(
            f"/api/invites/{token}/accept/",
            {"password": "otp-pass123"},
            format="json",
        )
        self.assertEqual(accept_res.status_code, 200)
