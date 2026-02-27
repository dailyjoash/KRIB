import base64
import logging
import os
import random
from datetime import datetime, timedelta

import json
from urllib import request as urllib_request
from urllib.error import HTTPError
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (
    Lease,
    ManagerInvite,
    MaintenanceRequest,
    Notification,
    PaymentTransaction,
    Profile,
    Property,
    Tenant,
    TenantInvite,
    Unit,
    compute_lease_rent_status,
)
from .serializers import (
    ChangePasswordSerializer,
    InviteAcceptSerializer,
    ManagerInviteAcceptSerializer,
    MeSerializer,
    LeaseSerializer,
    MaintenanceRequestSerializer,
    NotificationSerializer,
    ManagerInviteSerializer,
    PaymentTransactionSerializer,
    ProfileSerializer,
    PropertySerializer,
    STKInitiateSerializer,
    TenantInviteSerializer,
    TenantSerializer,
    UnitSerializer,
)

logger = logging.getLogger(__name__)


def _get_role(user):
    if hasattr(user, "profile"):
        return user.profile.role
    return Profile.ROLE_TENANT


def _scoped_properties(user):
    role = _get_role(user)
    if role == Profile.ROLE_LANDLORD:
        return Property.objects.filter(landlord=user)
    if role == Profile.ROLE_MANAGER:
        return Property.objects.filter(manager=user)
    if role == Profile.ROLE_TENANT:
        return Property.objects.filter(units__leases__tenant=user, units__leases__status=Lease.STATUS_ACTIVE).distinct()
    return Property.objects.none()


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def get_me(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response({
            "id": request.user.id,
            "username": request.user.username,
            "role": profile.role,
            "email": request.user.email,
            "phone_number": profile.phone_number,
        })

    serializer = MeSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data.get("email")
    phone_number = serializer.validated_data.get("phone_number")
    if email is not None:
        request.user.email = email
        request.user.save(update_fields=["email"])
    if phone_number is not None:
        profile.phone_number = phone_number
        profile.save(update_fields=["phone_number"])
    return Response({
        "id": request.user.id,
        "username": request.user.username,
        "role": profile.role,
        "email": request.user.email,
        "phone_number": profile.phone_number,
    })




@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    serializer = ChangePasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not request.user.check_password(serializer.validated_data["old_password"]):
        return Response({"old_password": ["Old password is incorrect."]}, status=400)
    request.user.set_password(serializer.validated_data["new_password"])
    request.user.save(update_fields=["password"])
    return Response({"detail": "Password changed successfully."})


def send_invite(invite):
    invite_link = f"http://localhost:5173/invite/{invite.token}"
    logger.info("Manager invite link: %s", invite_link)
    if getattr(settings, "EMAIL_HOST", ""):
        recipient = invite.email
        if recipient:
            send_mail(
                subject="KRIB Manager Invite",
                message=f"Use this link to join as manager: {invite_link}",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[recipient],
                fail_silently=True,
            )
    return invite_link


class ManagerInviteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD] and not request.user.is_staff:
            return Response({"detail": "Only landlord/admin can create manager invites."}, status=403)
        email = request.data.get("email")
        phone = request.data.get("phone")
        if not email and not phone:
            return Response({"detail": "Provide email or phone."}, status=400)
        invite = ManagerInvite.objects.create(
            created_by=request.user,
            email=email or None,
            phone=phone or None,
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True,
        )
        invite_link = send_invite(invite)
        return Response({
            "token": str(invite.token),
            "expires_at": invite.expires_at,
            "invite_link": invite_link,
        }, status=201)


class ManagerInviteAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ManagerInviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = ManagerInvite.objects.filter(token=serializer.validated_data["token"]).first()
        if not invite or not invite.is_active:
            return Response({"detail": "Invalid invite token."}, status=400)
        if invite.is_expired() or invite.accepted_at:
            return Response({"detail": "Invite is no longer valid."}, status=400)
        if User.objects.filter(username=serializer.validated_data["username"]).exists():
            return Response({"username": ["Username already exists."]}, status=400)

        user = User.objects.create(username=serializer.validated_data["username"], email=invite.email or "")
        user.set_password(serializer.validated_data["password"])
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = Profile.ROLE_MANAGER
        profile.phone_number = invite.phone
        profile.save(update_fields=["role", "phone_number"])
        invite.accepted_at = timezone.now()
        invite.is_active = False
        invite.save(update_fields=["accepted_at", "is_active"])
        return Response({"detail": "Invite accepted. Account created."})


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        role = _get_role(request.user)
        if role != Profile.ROLE_LANDLORD and not request.user.is_staff:
            return Response({"detail": "Forbidden"}, status=403)
        q = User.objects.all().select_related("profile")
        wanted_role = request.query_params.get("role")
        if wanted_role:
            q = q.filter(profile__role=wanted_role.lower())
        data = [{"id": u.id, "username": u.username} for u in q]
        return Response(data)

class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _scoped_properties(self.request.user)

    def perform_create(self, serializer):
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            raise PermissionDenied("Forbidden")
        landlord = self.request.user if role == Profile.ROLE_LANDLORD else self.request.user
        serializer.save(landlord=landlord)


class UnitViewSet(viewsets.ModelViewSet):
    serializer_class = UnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Unit.objects.filter(property__in=_scoped_properties(self.request.user)).select_related("property")

    def perform_create(self, serializer):
        prop = serializer.validated_data["property"]
        role = _get_role(self.request.user)
        if role == Profile.ROLE_MANAGER and prop.manager != self.request.user:
            raise PermissionDenied("You are not assigned to this property.")
        if role == Profile.ROLE_LANDLORD and prop.landlord != self.request.user:
            raise PermissionDenied("You do not own this property.")
        serializer.save()


class LeaseViewSet(viewsets.ModelViewSet):
    serializer_class = LeaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            return Lease.objects.filter(tenant=self.request.user).select_related("unit", "unit__property", "tenant")
        return Lease.objects.filter(unit__property__in=_scoped_properties(self.request.user)).select_related("unit", "unit__property", "tenant")

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["period"] = self.request.query_params.get("period")
        return ctx

    def perform_create(self, serializer):
        user = self.request.user
        role = _get_role(user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            raise PermissionDenied("Forbidden")
        unit = serializer.validated_data["unit"]
        if role == Profile.ROLE_MANAGER and unit.property.manager != user:
            raise PermissionDenied("Forbidden")
        if role == Profile.ROLE_LANDLORD and unit.property.landlord != user:
            raise PermissionDenied("Forbidden")
        serializer.save(rent_amount=unit.rent_amount)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        lease = self.get_object()
        lease.status = Lease.STATUS_INACTIVE
        lease.save(update_fields=["status"])
        lease.unit.status = Unit.STATUS_VACANT
        lease.unit.save(update_fields=["status"])
        return Response({"detail": "Lease deactivated."})


class InviteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = TenantInvite.objects.all()
    serializer_class = TenantInviteSerializer

    def get_queryset(self):
        if self.action in ["retrieve", "verify_otp", "accept"]:
            return TenantInvite.objects.all()
        role = _get_role(self.request.user)
        if role in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return TenantInvite.objects.filter(invited_by=self.request.user).order_by("-id")
        return TenantInvite.objects.none()

    def get_permissions(self):
        if self.action in ["retrieve", "verify_otp", "accept"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def create(self, request):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Response({"detail": "Only landlord/manager can invite."}, status=403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save(invited_by=request.user)
        if role == Profile.ROLE_MANAGER and invite.property and invite.property.manager != request.user:
            invite.delete()
            return Response({"detail": "Managers can only invite for assigned properties."}, status=403)
        Notification.objects.create(
            user=request.user, title="Invite created", message=f"Invite for {invite.full_name} created")
        logger.info("Invite link: /api/invites/%s/", invite.token)
        if invite.otp_code:
            logger.info("Invite OTP: %s", invite.otp_code)
        data = TenantInviteSerializer(invite).data
        data["invite_link"] = f"/api/invites/{invite.token}/"
        return Response(data, status=201)

    def retrieve(self, request, pk=None):
        invite = TenantInvite.objects.filter(token=pk).first()
        if not invite:
            return Response({"detail": "Not found"}, status=404)
        if invite.is_expired() and invite.status == TenantInvite.STATUS_PENDING:
            invite.status = TenantInvite.STATUS_EXPIRED
            invite.save(update_fields=["status"])
        return Response(TenantInviteSerializer(invite).data)


class InviteViewSet(viewsets.GenericViewSet):
    queryset = TenantInvite.objects.all()
    serializer_class = TenantInviteSerializer

    def get_permissions(self):
        if self.action in ["retrieve", "verify_otp", "accept"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def create(self, request):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Response({"detail": "Only landlord/manager can invite."}, status=403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save(invited_by=request.user)
        if role == Profile.ROLE_MANAGER and invite.property and invite.property.manager != request.user:
            invite.delete()
            return Response({"detail": "Managers can only invite for assigned properties."}, status=403)
        Notification.objects.create(
            user=request.user, title="Invite created", message=f"Invite for {invite.full_name} created")
        logger.info("Invite link: /api/invites/%s/", invite.token)
        if invite.otp_code:
            logger.info("Invite OTP: %s", invite.otp_code)
        data = TenantInviteSerializer(invite).data
        data["invite_link"] = f"/api/invites/{invite.token}/"
        return Response(data, status=201)

    def retrieve(self, request, pk=None):
        invite = TenantInvite.objects.filter(token=pk).first()
        if not invite:
            return Response({"detail": "Not found"}, status=404)
        if invite.is_expired() and invite.status == TenantInvite.STATUS_PENDING:
            invite.status = TenantInvite.STATUS_EXPIRED
            invite.save(update_fields=["status"])
        return Response(TenantInviteSerializer(invite).data)

    @action(detail=True, methods=["post"], url_path="verify-otp")
    def verify_otp(self, request, pk=None):
        invite = TenantInvite.objects.filter(token=pk).first()
        if not invite:
            return Response({"detail": "Not found"}, status=404)
        otp = request.data.get("otp_code")
        if not invite.otp_code:
            return Response({"detail": "OTP not enabled for this invite."}, status=400)
        if invite.otp_expires_at and timezone.now() > invite.otp_expires_at:
            return Response({"detail": "OTP expired."}, status=400)
        if otp != invite.otp_code:
            return Response({"detail": "Invalid OTP."}, status=400)
        return Response({"detail": "OTP verified."})

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        invite = TenantInvite.objects.filter(token=pk).first()
        if not invite:
            return Response({"detail": "Not found"}, status=404)
        if invite.is_expired() or invite.status != TenantInvite.STATUS_PENDING:
            return Response({"detail": "Invite is no longer valid."}, status=400)
        serializer = InviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data.get("username") or (
            invite.email or invite.phone or f"tenant_{invite.token.hex[:8]}")
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": invite.email or ""})
        user.set_password(serializer.validated_data["password"])
        user.email = invite.email or user.email
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = Profile.ROLE_TENANT
        profile.save(update_fields=["role"])
        tenant_profile, _ = Tenant.objects.get_or_create(user=user)
        if invite.phone:
            tenant_profile.phone = invite.phone
            tenant_profile.save(update_fields=["phone"])
        invite.status = TenantInvite.STATUS_ACCEPTED
        invite.save(update_fields=["status"])
        Notification.objects.create(
            user=user, title="Welcome to KRIB", message="Your tenant account has been activated.")
        return Response({"detail": "Invite accepted.", "username": user.username, "created": created})


class STKInitiateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Only tenants can initiate payment."}, status=403)
        serializer = STKInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lease = serializer.validated_data["lease"]
        if lease.tenant != request.user or lease.status != Lease.STATUS_ACTIVE:
            return Response({"detail": "You can only pay your active lease."}, status=403)
        period = timezone.localdate().strftime("%Y-%m")
        payment = PaymentTransaction.objects.create(
            lease=lease,
            tenant=request.user,
            period=period,
            phone_number=serializer.validated_data["phone_number"],
            amount=serializer.validated_data["amount"],
            status=PaymentTransaction.STATUS_PENDING,
        )
        result = initiate_stk_push(payment)
        payment.merchant_request_id = result.get("MerchantRequestID")
        payment.checkout_request_id = result.get("CheckoutRequestID")
        if result.get("errorMessage"):
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.result_desc = result.get("errorMessage")
        payment.raw_callback = result
        payment.save()
        return Response(PaymentTransactionSerializer(payment).data, status=201)


class STKCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.data
        callback = payload.get("Body", {}).get("stkCallback", {})
        checkout_id = callback.get("CheckoutRequestID")
        payment = PaymentTransaction.objects.filter(
            checkout_request_id=checkout_id).first()
        if not payment:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})
        result_code = callback.get("ResultCode")
        payment.result_code = result_code
        payment.result_desc = callback.get("ResultDesc")
        payment.raw_callback = payload
        if result_code == 0:
            payment.status = PaymentTransaction.STATUS_SUCCESS
            metadata = callback.get("CallbackMetadata", {}).get("Item", [])
            parsed = {item.get("Name"): item.get("Value") for item in metadata}
            payment.mpesa_receipt = parsed.get("MpesaReceiptNumber")
            tr_date = parsed.get("TransactionDate")
            if tr_date:
                payment.transaction_date = datetime.strptime(
                    str(tr_date), "%Y%m%d%H%M%S")
        else:
            payment.status = PaymentTransaction.STATUS_FAILED
        payment.save()
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            return PaymentTransaction.objects.filter(tenant=self.request.user).select_related("lease", "lease__unit")
        if role == Profile.ROLE_LANDLORD:
            return PaymentTransaction.objects.all().select_related("lease", "lease__unit", "lease__unit__property")
        if role == Profile.ROLE_MANAGER:
            return PaymentTransaction.objects.filter(lease__unit__property__manager=self.request.user).select_related("lease", "lease__unit")
        return PaymentTransaction.objects.none()


class MaintenanceViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            return MaintenanceRequest.objects.filter(tenant=self.request.user).select_related("lease", "lease__unit")
        if role == Profile.ROLE_LANDLORD:
            return MaintenanceRequest.objects.filter(lease__unit__property__landlord=self.request.user).select_related("lease", "tenant")
        if role == Profile.ROLE_MANAGER:
            return MaintenanceRequest.objects.filter(lease__unit__property__manager=self.request.user).select_related("lease", "tenant")
        return MaintenanceRequest.objects.none()

    def perform_create(self, serializer):
        if _get_role(self.request.user) != Profile.ROLE_TENANT:
            raise PermissionDenied("Only tenants can create requests")
        lease = serializer.validated_data["lease"]
        if lease.tenant != self.request.user or lease.status != Lease.STATUS_ACTIVE:
            raise ValidationError("Active lease required")
        maintenance = serializer.save(tenant=self.request.user)
        recipients = [lease.unit.property.landlord]
        if lease.unit.property.manager:
            recipients.append(lease.unit.property.manager)
        for user in recipients:
            Notification.objects.create(user=user, title="Maintenance request",
                                        message=f"New issue from {self.request.user.username}: {maintenance.issue}")

    def perform_update(self, serializer):
        prev = self.get_object()
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            raise PermissionDenied("Tenants cannot update status")
        updated = serializer.save()
        if prev.status != updated.status:
            Notification.objects.create(user=updated.tenant, title="Maintenance updated",
                                        message=f"Your request status is now {updated.status}.")


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Tenant.objects.select_related("user").all()
        if role == Profile.ROLE_TENANT:
            return Tenant.objects.filter(user=self.request.user).select_related("user")
        return Tenant.objects.none()


class STKInitiateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Only tenants can initiate payment."}, status=403)
        serializer = STKInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lease = serializer.validated_data["lease"]
        if lease.tenant != request.user or lease.status != Lease.STATUS_ACTIVE:
            return Response({"detail": "You can only pay your active lease."}, status=403)
        period = timezone.localdate().strftime("%Y-%m")
        payment = PaymentTransaction.objects.create(
            lease=lease,
            tenant=request.user,
            period=period,
            phone_number=serializer.validated_data["phone_number"],
            amount=serializer.validated_data["amount"],
            status=PaymentTransaction.STATUS_PENDING,
        )
        result = initiate_stk_push(payment)
        payment.merchant_request_id = result.get("MerchantRequestID")
        payment.checkout_request_id = result.get("CheckoutRequestID")
        if result.get("errorMessage"):
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.result_desc = result.get("errorMessage")
        payment.raw_callback = result
        payment.save()
        return Response(PaymentTransactionSerializer(payment).data, status=201)


class STKCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.data
        callback = payload.get("Body", {}).get("stkCallback", {})
        checkout_id = callback.get("CheckoutRequestID")
        payment = PaymentTransaction.objects.filter(
            checkout_request_id=checkout_id).first()
        if not payment:
            return Response({"ResultCode": 0, "ResultDesc": "Accepted"})
        result_code = callback.get("ResultCode")
        payment.result_code = result_code
        payment.result_desc = callback.get("ResultDesc")
        payment.raw_callback = payload
        if result_code == 0:
            payment.status = PaymentTransaction.STATUS_SUCCESS
            metadata = callback.get("CallbackMetadata", {}).get("Item", [])
            parsed = {item.get("Name"): item.get("Value") for item in metadata}
            payment.mpesa_receipt = parsed.get("MpesaReceiptNumber")
            tr_date = parsed.get("TransactionDate")
            if tr_date:
                payment.transaction_date = datetime.strptime(
                    str(tr_date), "%Y%m%d%H%M%S")
        else:
            payment.status = PaymentTransaction.STATUS_FAILED
        payment.save()
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Tenant.objects.select_related("user").all()
        if role == Profile.ROLE_TENANT:
            return Tenant.objects.filter(user=self.request.user).select_related("user")
        return Tenant.objects.none()
        if role == Profile.ROLE_TENANT:
            return PaymentTransaction.objects.filter(tenant=self.request.user).select_related("lease", "lease__unit")
        if role == Profile.ROLE_LANDLORD:
            return PaymentTransaction.objects.all().select_related("lease", "lease__unit", "lease__unit__property")
        if role == Profile.ROLE_MANAGER:
            return PaymentTransaction.objects.filter(lease__unit__property__manager=self.request.user).select_related("lease", "lease__unit")
        return PaymentTransaction.objects.none()


class MaintenanceViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            return MaintenanceRequest.objects.filter(tenant=self.request.user).select_related("lease", "lease__unit")
        if role == Profile.ROLE_LANDLORD:
            return MaintenanceRequest.objects.filter(lease__unit__property__landlord=self.request.user).select_related("lease", "tenant")
        if role == Profile.ROLE_MANAGER:
            return MaintenanceRequest.objects.filter(lease__unit__property__manager=self.request.user).select_related("lease", "tenant")
        return MaintenanceRequest.objects.none()

    def perform_create(self, serializer):
        if _get_role(self.request.user) != Profile.ROLE_TENANT:
            raise PermissionDenied("Only tenants can create requests")
        lease = serializer.validated_data["lease"]
        if lease.tenant != self.request.user or lease.status != Lease.STATUS_ACTIVE:
            raise ValidationError("Active lease required")
        maintenance = serializer.save(tenant=self.request.user)
        recipients = [lease.unit.property.landlord]
        if lease.unit.property.manager:
            recipients.append(lease.unit.property.manager)
        for user in recipients:
            Notification.objects.create(user=user, title="Maintenance request",
                                        message=f"New issue from {self.request.user.username}: {maintenance.issue}")

    def perform_update(self, serializer):
        prev = self.get_object()
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            raise PermissionDenied("Tenants cannot update status")
        updated = serializer.save()
        if prev.status != updated.status:
            Notification.objects.create(user=updated.tenant, title="Maintenance updated",
                                        message=f"Your request status is now {updated.status}.")


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    period = timezone.localdate().strftime("%Y-%m")
    role = _get_role(request.user)
    if role == Profile.ROLE_TENANT:
        active_lease = Lease.objects.filter(
            tenant=request.user, status=Lease.STATUS_ACTIVE).select_related("unit", "unit__property").first()
        if not active_lease:
            return Response({"active_lease": None, "payments": []})
        status_data = compute_lease_rent_status(active_lease, period=period)
        show_overdue_banner = status_data["status"] == "OVERDUE"
        payments = PaymentTransaction.objects.filter(
            lease=active_lease).order_by("-created_at")
        return Response({
            "active_lease": LeaseSerializer(active_lease).data,
            "rent": status_data,
            "show_overdue_banner": show_overdue_banner,
            "payments": PaymentTransactionSerializer(payments, many=True).data,
        })

    leases = Lease.objects.filter(status=Lease.STATUS_ACTIVE)
    if role == Profile.ROLE_MANAGER:
        leases = leases.filter(unit__property__manager=request.user)
    elif role == Profile.ROLE_LANDLORD:
        leases = leases.filter(unit__property__landlord=request.user)
    else:
        leases = Lease.objects.none()

    grouped = {"PAID": [], "PARTIAL": [], "UNPAID": [], "OVERDUE": []}
    totals = {"expected": 0, "collected": 0, "outstanding": 0}
    for lease in leases.select_related("tenant", "unit"):
        data = compute_lease_rent_status(lease, period=period)
        row = {
            "lease_id": lease.id,
            "tenant": lease.tenant.username,
            "unit": f"{lease.unit.property.name} / {lease.unit.unit_number}",
            "rent_due": data["rent_due"],
            "paid_sum": data["paid_sum"],
            "balance": data["balance"],
            "status": data["status"],
        }
        grouped[data["status"]].append(row)
        totals["expected"] += float(data["rent_due"])
        totals["collected"] += float(data["paid_sum"])
        totals["outstanding"] += float(max(data["balance"], 0))
    return Response({"period": period, "lists": grouped, "totals": totals})


def _daraja_access_token():
    key = os.getenv("DARAJA_CONSUMER_KEY")
    secret = os.getenv("DARAJA_CONSUMER_SECRET")
    env = os.getenv("DARAJA_ENV", "sandbox")
    base = "https://api.safaricom.co.ke" if env == "production" else "https://sandbox.safaricom.co.ke"
    credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req = urllib_request.Request(
        f"{base}/oauth/v1/generate?grant_type=client_credentials")
    req.add_header("Authorization", f"Basic {credentials}")
    with urllib_request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    return payload.get("access_token"), base


def initiate_stk_push(payment):
    shortcode = os.getenv("DARAJA_SHORTCODE", "")
    passkey = os.getenv("DARAJA_PASSKEY", "")
    callback_url = os.getenv("DARAJA_CALLBACK_URL", "")
    if not all([shortcode, passkey, callback_url]):
        return {"errorMessage": "Daraja credentials not fully configured."}
    token, base = _daraja_access_token()
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{shortcode}{passkey}{timestamp}".encode()).decode()
    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(payment.amount),
        "PartyA": payment.phone_number,
        "PartyB": shortcode,
        "PhoneNumber": payment.phone_number,
        "CallBackURL": callback_url,
        "AccountReference": f"KRIB-{payment.lease.id}",
        "TransactionDesc": f"Rent payment {payment.period}",
    }
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib_request.Request(
        f"{base}/mpesa/stkpush/v1/processrequest",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        return {"errorMessage": exc.read().decode()}
