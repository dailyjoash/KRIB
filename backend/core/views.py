import base64
import json
import logging
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal
from urllib import request as urllib_request
from urllib.error import HTTPError

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    LandlordBalance,
    LandlordSettings,
    LandlordPayout,
    Lease,
    LedgerTransaction,
    MaintenanceRequest,
    ManagerInvite,
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
    LandlordFollowupSerializer,
    LandlordReceiptSerializer,
    LandlordRevenueSerializer,
    LandlordSignupSerializer,
    InviteAcceptSerializer,
    LandlordPayoutRequestSerializer,
    LandlordPayoutSerializer,
    LeaseSerializer,
    LedgerTransactionSerializer,
    MaintenanceRequestSerializer,
    ManagerInviteAcceptSerializer,
    MeSerializer,
    NotificationSerializer,
    PaymentTransactionSerializer,
    PropertySerializer,
    STKInitiateSerializer,
    TenantInviteSerializer,
    TenantSerializer,
    UnitSerializer,
    WalletWithdrawSerializer,
)

logger = logging.getLogger(__name__)
LANDLORD_HOLD_DAYS = 2
WALLET_WITHDRAW_HOLD_DAYS = 7
WALLET_CREDIT_HOLD_DAYS = 7


def _get_role(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile.role


def _scoped_properties(user):
    role = _get_role(user)
    if role == Profile.ROLE_LANDLORD:
        return Property.objects.filter(landlord=user)
    if role == Profile.ROLE_MANAGER:
        return Property.objects.filter(manager=user)
    if role == Profile.ROLE_TENANT:
        return Property.objects.filter(units__leases__tenant=user, units__leases__status=Lease.STATUS_ACTIVE).distinct()
    return Property.objects.none()


def _unlock_wallet(profile):
    now = timezone.now()
    rows = LedgerTransaction.objects.filter(
        user=profile.user,
        kind=LedgerTransaction.KIND_WALLET_CREDIT,
        status=LedgerTransaction.STATUS_LOCKED,
        available_at__lte=now,
    )
    amount = sum((row.amount for row in rows), Decimal("0.00"))
    if amount > 0:
        rows.update(status=LedgerTransaction.STATUS_AVAILABLE)
        profile.wallet_locked = max(profile.wallet_locked - amount, Decimal("0.00"))
        profile.wallet_available += amount
        profile.save(update_fields=["wallet_locked", "wallet_available", "updated_at"])


def _unlock_landlord(balance):
    now = timezone.now()
    rows = LedgerTransaction.objects.filter(
        user=balance.landlord,
        kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
        status=LedgerTransaction.STATUS_LOCKED,
        available_at__lte=now,
    )
    amount = sum((row.amount for row in rows), Decimal("0.00"))
    if amount > 0:
        rows.update(status=LedgerTransaction.STATUS_AVAILABLE)
        balance.locked_balance = max(balance.locked_balance - amount, Decimal("0.00"))
        balance.available_balance += amount
        balance.save(update_fields=["locked_balance", "available_balance", "updated_at"])


def _apply_wallet_to_current_rent(lease):
    profile, _ = Profile.objects.get_or_create(user=lease.tenant)
    _unlock_wallet(profile)
    rent_status = compute_lease_rent_status(lease)
    due = max(rent_status["balance"], Decimal("0.00"))
    if due <= 0 or profile.wallet_available <= 0:
        return Decimal("0.00")
    debit = min(profile.wallet_available, due)
    if debit <= 0:
        return Decimal("0.00")

    period = timezone.localdate().strftime("%Y-%m")
    PaymentTransaction.objects.create(
        lease=lease,
        tenant=lease.tenant,
        period=period,
        phone_number=profile.phone_number or "WALLET",
        amount=debit,
        status=PaymentTransaction.STATUS_SUCCESS,
        result_desc="Auto wallet rent debit",
        transaction_date=timezone.now(),
        allocation_done=True,
    )
    profile.wallet_available -= debit
    profile.save(update_fields=["wallet_available", "updated_at"])
    LedgerTransaction.objects.create(
        user=lease.tenant,
        kind=LedgerTransaction.KIND_WALLET_DEBIT_RENT,
        amount=debit,
        status=LedgerTransaction.STATUS_PAID,
        reference_text=f"lease:{lease.id};period:{period}",
    )
    landlord = lease.unit.property.landlord
    lb, _ = LandlordBalance.objects.get_or_create(landlord=landlord)
    lb.locked_balance += debit
    lb.save(update_fields=["locked_balance", "updated_at"])
    LedgerTransaction.objects.create(
        user=landlord,
        kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
        amount=debit,
        status=LedgerTransaction.STATUS_LOCKED,
        available_at=timezone.now() + timedelta(days=LANDLORD_HOLD_DAYS),
        reference_text=f"wallet_debit_lease:{lease.id}",
    )
    return debit


def _allocate_success_payment(payment):
    if payment.allocation_done or payment.status != PaymentTransaction.STATUS_SUCCESS:
        return

    lease = payment.lease
    landlord = lease.unit.property.landlord
    profile, _ = Profile.objects.get_or_create(user=payment.tenant)
    landlord_balance, _ = LandlordBalance.objects.get_or_create(landlord=landlord)

    with transaction.atomic():
        rent_status = compute_lease_rent_status(lease, period=payment.period)
        due_before = max(rent_status["balance"] + payment.amount, Decimal("0.00"))
        rent_applied = min(payment.amount, due_before)
        overpayment = payment.amount - rent_applied

        if rent_applied > 0:
            landlord_balance.locked_balance += rent_applied
            landlord_balance.save(update_fields=["locked_balance", "updated_at"])
            LedgerTransaction.objects.create(
                user=landlord,
                kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
                amount=rent_applied,
                status=LedgerTransaction.STATUS_LOCKED,
                available_at=timezone.now() + timedelta(days=LANDLORD_HOLD_DAYS),
                reference_text=f"payment:{payment.id};lease:{lease.id}",
            )

        if overpayment > 0:
            profile.wallet_locked += overpayment
            profile.save(update_fields=["wallet_locked", "updated_at"])
            LedgerTransaction.objects.create(
                user=payment.tenant,
                kind=LedgerTransaction.KIND_WALLET_CREDIT,
                amount=overpayment,
                status=LedgerTransaction.STATUS_LOCKED,
                available_at=timezone.now() + timedelta(days=WALLET_CREDIT_HOLD_DAYS),
                reference_text=f"payment:{payment.id};lease:{lease.id}",
            )

        payment.allocation_done = True
        payment.save(update_fields=["allocation_done"])


def _daraja_access_token():
    key = os.getenv("MPESA_CONSUMER_KEY", "")
    secret = os.getenv("MPESA_CONSUMER_SECRET", "")
    if not key or not secret:
        return None
    auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
    req = urllib_request.Request(
        os.getenv("MPESA_OAUTH_URL", "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"),
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib_request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode())
        return payload.get("access_token")


def _daraja_stk_push(phone_number, amount, reference):
    shortcode = os.getenv("MPESA_SHORTCODE", "")
    passkey = os.getenv("MPESA_PASSKEY", "")
    callback_url = os.getenv("MPESA_CALLBACK_URL", "")
    if not shortcode or not passkey or not callback_url:
        return None

    token = _daraja_access_token()
    if not token:
        return None

    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(f"{shortcode}{passkey}{timestamp}".encode()).decode()

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(Decimal(amount)),
        "PartyA": phone_number,
        "PartyB": shortcode,
        "PhoneNumber": phone_number,
        "CallBackURL": callback_url,
        "AccountReference": reference,
        "TransactionDesc": "KRIB rent payment",
    }

    req = urllib_request.Request(
        os.getenv("MPESA_STK_PUSH_URL", "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"),
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as exc:
        logger.warning("Daraja STK push failed: %s", exc.read().decode())
        return None


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def get_me(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "role": profile.role,
                "is_staff": request.user.is_staff,
                "email": request.user.email,
                "phone_number": profile.phone_number,
            }
        )

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

    return Response(
        {
            "id": request.user.id,
            "username": request.user.username,
            "role": profile.role,
            "is_staff": request.user.is_staff,
            "email": request.user.email,
            "phone_number": profile.phone_number,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def signup_landlord(request):
    serializer = LandlordSignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        user = User.objects.create(
            username=serializer.validated_data["username"],
            email=serializer.validated_data.get("email", ""),
        )
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = Profile.ROLE_LANDLORD
        profile.phone_number = serializer.validated_data.get("phone_number") or ""
        profile.save(update_fields=["role", "phone_number"])

        LandlordSettings.objects.update_or_create(
            user=user,
            defaults={"business_name": serializer.validated_data["business_name"]},
        )

    return Response({"detail": "Landlord account created successfully."}, status=201)


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
    if getattr(settings, "EMAIL_HOST", "") and invite.email:
        send_mail(
            subject="KRIB Manager Invite",
            message=f"Use this link to join as manager: {invite_link}",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[invite.email],
            fail_silently=True,
        )
    return invite_link


class ManagerInviteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = _get_role(request.user)
        if role != Profile.ROLE_LANDLORD and not request.user.is_staff:
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
        return Response({"token": str(invite.token), "expires_at": invite.expires_at, "invite_link": send_invite(invite)}, status=201)


class ManagerInviteAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ManagerInviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = ManagerInvite.objects.filter(token=serializer.validated_data["token"], is_active=True).first()
        if not invite:
            return Response({"detail": "Invalid invite token."}, status=400)
        if invite.is_expired() or invite.accepted_at:
            return Response({"detail": "Invite expired or already used."}, status=400)

        user, created = User.objects.get_or_create(
            username=serializer.validated_data["username"], defaults={"email": invite.email or ""}
        )
        user.set_password(serializer.validated_data["password"])
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = Profile.ROLE_MANAGER
        profile.save(update_fields=["role"])
        invite.accepted_at = timezone.now()
        invite.is_active = False
        invite.save(update_fields=["accepted_at", "is_active"])
        return Response({"detail": "Manager invite accepted.", "created": created})


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all().order_by("id")
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]


class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _scoped_properties(self.request.user).order_by("id")

    def perform_create(self, serializer):
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord can create properties")
        serializer.save(landlord=self.request.user)


class UnitViewSet(viewsets.ModelViewSet):
    serializer_class = UnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        props = _scoped_properties(self.request.user)
        return Unit.objects.filter(property__in=props).select_related("property").order_by("id")


class LeaseViewSet(viewsets.ModelViewSet):
    serializer_class = LeaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == Profile.ROLE_TENANT:
            return Lease.objects.filter(tenant=user).select_related("unit", "unit__property", "tenant")
        return Lease.objects.filter(unit__property__in=_scoped_properties(user)).select_related("unit", "unit__property", "tenant")


class InviteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = TenantInvite.objects.all().order_by("-id")
    serializer_class = TenantInviteSerializer

    def get_permissions(self):
        if self.action in ["retrieve", "verify_otp", "accept"]:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if self.action in ["retrieve", "verify_otp", "accept"]:
            return TenantInvite.objects.all()
        role = _get_role(self.request.user)
        if role == Profile.ROLE_LANDLORD:
            return TenantInvite.objects.filter(invited_by=self.request.user)
        if role == Profile.ROLE_MANAGER:
            return TenantInvite.objects.filter(property__manager=self.request.user)
        return TenantInvite.objects.none()

    def create(self, request, *args, **kwargs):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Response({"detail": "Only landlord/manager can invite."}, status=403)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save(invited_by=request.user)
        if role == Profile.ROLE_MANAGER and invite.property and invite.property.manager != request.user:
            invite.delete()
            return Response({"detail": "Managers can only invite for assigned properties."}, status=403)
        data = TenantInviteSerializer(invite).data
        data["invite_link"] = f"/api/invites/{invite.token}/"
        return Response(data, status=201)

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
        username = serializer.validated_data.get("username") or (invite.email or invite.phone or f"tenant_{invite.token.hex[:8]}")
        user, created = User.objects.get_or_create(username=username, defaults={"email": invite.email or ""})
        user.set_password(serializer.validated_data["password"])
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

        _apply_wallet_to_current_rent(lease)
        period = timezone.localdate().strftime("%Y-%m")
        payment = PaymentTransaction.objects.create(
            lease=lease,
            tenant=request.user,
            period=period,
            phone_number=serializer.validated_data["phone_number"],
            amount=serializer.validated_data["amount"],
            status=PaymentTransaction.STATUS_PENDING,
        )

        result = _daraja_stk_push(payment.phone_number, payment.amount, f"LEASE-{lease.id}")
        if result:
            payment.merchant_request_id = result.get("MerchantRequestID")
            payment.checkout_request_id = result.get("CheckoutRequestID")
            payment.result_code = result.get("ResponseCode")
            payment.result_desc = result.get("ResponseDescription")
            payment.save(update_fields=["merchant_request_id", "checkout_request_id", "result_code", "result_desc"])

        return Response({"detail": "STK push initiated.", "payment": PaymentTransactionSerializer(payment).data}, status=201)


class STKCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        body = request.data.get("Body", {})
        callback = body.get("stkCallback", {})
        checkout_request_id = callback.get("CheckoutRequestID")
        result_code = callback.get("ResultCode")
        result_desc = callback.get("ResultDesc")
        items = callback.get("CallbackMetadata", {}).get("Item", [])

        metadata = {item.get("Name"): item.get("Value") for item in items if "Name" in item}
        mpesa_receipt = metadata.get("MpesaReceiptNumber")
        transaction_date = metadata.get("TransactionDate")

        payment = PaymentTransaction.objects.filter(checkout_request_id=checkout_request_id).first()
        if not payment:
            return Response({"detail": "No matching payment."}, status=404)

        payment.raw_callback = request.data
        payment.result_code = result_code
        payment.result_desc = result_desc
        payment.mpesa_receipt = mpesa_receipt
        if transaction_date:
            try:
                payment.transaction_date = datetime.strptime(str(transaction_date), "%Y%m%d%H%M%S")
            except ValueError:
                payment.transaction_date = timezone.now()

        payment.status = PaymentTransaction.STATUS_SUCCESS if result_code == 0 else PaymentTransaction.STATUS_FAILED
        payment.save(
            update_fields=["raw_callback", "result_code", "result_desc", "mpesa_receipt", "transaction_date", "status"]
        )
        if payment.status == PaymentTransaction.STATUS_SUCCESS:
            _allocate_success_payment(payment)
        return Response({"detail": "Callback processed."})


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        qs = PaymentTransaction.objects.select_related("lease", "lease__unit", "lease__unit__property", "tenant")
        if role == Profile.ROLE_TENANT:
            qs = qs.filter(tenant=self.request.user)
        elif role == Profile.ROLE_MANAGER:
            qs = qs.filter(lease__unit__property__manager=self.request.user)
        elif role == Profile.ROLE_LANDLORD:
            qs = qs.filter(lease__unit__property__landlord=self.request.user)
        else:
            return qs.none()

        period = self.request.query_params.get("period")
        if period:
            qs = qs.filter(period=period)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())

        return qs.order_by("-created_at")


class MaintenanceViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        qs = MaintenanceRequest.objects.select_related("tenant", "lease", "lease__unit", "lease__unit__property")
        if role == Profile.ROLE_TENANT:
            return qs.filter(tenant=self.request.user).order_by("-updated_at")
        if role == Profile.ROLE_MANAGER:
            return qs.filter(lease__unit__property__manager=self.request.user).order_by("-updated_at")
        if role == Profile.ROLE_LANDLORD:
            return qs.filter(lease__unit__property__landlord=self.request.user).order_by("-updated_at")
        return qs.none()

    def perform_create(self, serializer):
        role = _get_role(self.request.user)
        if role != Profile.ROLE_TENANT:
            raise PermissionDenied("Only tenants can create maintenance requests")
        lease = serializer.validated_data["lease"]
        if lease.tenant != self.request.user:
            raise PermissionDenied("Can only report for your lease")
        serializer.save(tenant=self.request.user)


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_LANDLORD:
            return Tenant.objects.filter(user__leases__unit__property__landlord=self.request.user).distinct()
        if role == Profile.ROLE_MANAGER:
            return Tenant.objects.filter(user__leases__unit__property__manager=self.request.user).distinct()
        return Tenant.objects.filter(user=self.request.user)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    role = _get_role(request.user)
    period = request.query_params.get("period") or timezone.localdate().strftime("%Y-%m")

    if role == Profile.ROLE_TENANT:
        lease = (
            Lease.objects.filter(tenant=request.user, status=Lease.STATUS_ACTIVE)
            .select_related("unit", "unit__property")
            .first()
        )
        if not lease:
            return Response({"active_lease": None, "rent": {}, "payments": [], "maintenance": [], "show_overdue_banner": False})
        _apply_wallet_to_current_rent(lease)
        rent = compute_lease_rent_status(lease, period=period)
        payments = PaymentTransaction.objects.filter(tenant=request.user).order_by("-created_at")[:10]
        maintenance = MaintenanceRequest.objects.filter(tenant=request.user).order_by("-updated_at")[:10]
        return Response(
            {
                "period": period,
                "active_lease": LeaseSerializer(lease, context={"period": period}).data,
                "rent": rent,
                "payments": PaymentTransactionSerializer(payments, many=True).data,
                "maintenance": MaintenanceRequestSerializer(maintenance, many=True).data,
                "show_overdue_banner": rent.get("status") == "OVERDUE",
            }
        )

    leases = Lease.objects.filter(status=Lease.STATUS_ACTIVE)
    if role == Profile.ROLE_MANAGER:
        leases = leases.filter(unit__property__manager=request.user)
    elif role == Profile.ROLE_LANDLORD:
        leases = leases.filter(unit__property__landlord=request.user)

    lists = {"PAID": [], "PARTIAL": [], "UNPAID": [], "OVERDUE": []}
    expected = Decimal("0.00")
    collected = Decimal("0.00")
    outstanding = Decimal("0.00")

    for lease in leases.select_related("tenant", "unit", "unit__property"):
        status_row = compute_lease_rent_status(lease, period=period)
        expected += status_row["rent_due"]
        collected += status_row["paid_sum"]
        outstanding += max(status_row["balance"], Decimal("0.00"))
        lists[status_row["status"]].append(
            {
                "lease_id": lease.id,
                "tenant": lease.tenant.username,
                "unit": f"{lease.unit.property.name} / {lease.unit.unit_number}",
                "rent_due": status_row["rent_due"],
                "paid_sum": status_row["paid_sum"],
                "balance": status_row["balance"],
                "status": status_row["status"],
            }
        )

    maintenance_qs = MaintenanceRequest.objects.select_related("tenant", "lease", "lease__unit", "lease__unit__property")
    if role == Profile.ROLE_MANAGER:
        maintenance_qs = maintenance_qs.filter(lease__unit__property__manager=request.user)
    elif role == Profile.ROLE_LANDLORD:
        maintenance_qs = maintenance_qs.filter(lease__unit__property__landlord=request.user)

    return Response(
        {
            "period": period,
            "totals": {"expected": expected, "collected": collected, "outstanding": outstanding},
            "lists": lists,
            "maintenance": MaintenanceRequestSerializer(maintenance_qs.order_by("-updated_at")[:20], many=True).data,
        }
    )


class WalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Tenant only endpoint"}, status=403)
        profile, _ = Profile.objects.get_or_create(user=request.user)
        _unlock_wallet(profile)
        recent = LedgerTransaction.objects.filter(user=request.user, kind__startswith="WALLET").order_by("-created_at")[:20]
        pending_withdrawals = LedgerTransaction.objects.filter(
            user=request.user,
            kind=LedgerTransaction.KIND_WALLET_WITHDRAW_REQUEST,
            status=LedgerTransaction.STATUS_PENDING,
        ).order_by("-created_at")
        return Response(
            {
                "wallet_available": profile.wallet_available,
                "wallet_locked": profile.wallet_locked,
                "recent": LedgerTransactionSerializer(recent, many=True).data,
                "pending_withdrawals": LedgerTransactionSerializer(pending_withdrawals, many=True).data,
            }
        )


class WalletWithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Tenant only endpoint"}, status=403)
        serializer = WalletWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]
        if amount <= 0:
            return Response({"detail": "Amount must be greater than zero"}, status=400)
        profile, _ = Profile.objects.get_or_create(user=request.user)
        _unlock_wallet(profile)
        if amount > profile.wallet_available:
            return Response({"detail": "Insufficient wallet balance"}, status=400)

        profile.wallet_available -= amount
        profile.save(update_fields=["wallet_available", "updated_at"])
        row = LedgerTransaction.objects.create(
            user=request.user,
            kind=LedgerTransaction.KIND_WALLET_WITHDRAW_REQUEST,
            amount=amount,
            status=LedgerTransaction.STATUS_PENDING,
            available_at=timezone.now() + timedelta(days=WALLET_WITHDRAW_HOLD_DAYS),
            reference_text="Withdrawals are processed after 7 days",
        )
        return Response(LedgerTransactionSerializer(row).data, status=201)


class WalletWithdrawalMarkPaidView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Admin only endpoint"}, status=403)
        row = LedgerTransaction.objects.filter(
            pk=pk,
            kind=LedgerTransaction.KIND_WALLET_WITHDRAW_REQUEST,
        ).first()
        if not row:
            return Response({"detail": "Withdrawal request not found"}, status=404)
        row.status = LedgerTransaction.STATUS_PAID
        row.save(update_fields=["status"])
        LedgerTransaction.objects.create(
            user=row.user,
            kind=LedgerTransaction.KIND_WALLET_WITHDRAW_PAID,
            amount=row.amount,
            status=LedgerTransaction.STATUS_PAID,
            reference_text=f"withdrawal:{row.id}",
        )
        return Response({"detail": "Withdrawal marked paid"})


class LandlordPayoutsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _get_role(request.user) != Profile.ROLE_LANDLORD:
            return Response({"detail": "Landlord only endpoint"}, status=403)
        balance, _ = LandlordBalance.objects.get_or_create(landlord=request.user)
        _unlock_landlord(balance)
        payouts = LandlordPayout.objects.filter(landlord=request.user).order_by("-created_at")
        return Response(
            {
                "available_balance": balance.available_balance,
                "locked_balance": balance.locked_balance,
                "payout_requests": LandlordPayoutSerializer(payouts, many=True).data,
            }
        )


class LandlordPayoutRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_LANDLORD:
            return Response({"detail": "Landlord only endpoint"}, status=403)
        serializer = LandlordPayoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]
        if amount <= 0:
            return Response({"detail": "Amount must be greater than zero"}, status=400)

        balance, _ = LandlordBalance.objects.get_or_create(landlord=request.user)
        _unlock_landlord(balance)
        if amount > balance.available_balance:
            return Response({"detail": "Insufficient available balance"}, status=400)

        balance.available_balance -= amount
        balance.save(update_fields=["available_balance", "updated_at"])
        payout = LandlordPayout.objects.create(
            landlord=request.user,
            amount=amount,
            method=serializer.validated_data["method"],
            destination=serializer.validated_data["destination"],
            status=LandlordPayout.STATUS_PENDING,
        )
        LedgerTransaction.objects.create(
            user=request.user,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
            amount=amount,
            status=LedgerTransaction.STATUS_PENDING,
            reference_text=f"payout:{payout.id}",
        )
        return Response(LandlordPayoutSerializer(payout).data, status=201)


class LandlordPayoutMarkPaidView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Admin only endpoint"}, status=403)
        payout = LandlordPayout.objects.filter(pk=pk).first()
        if not payout:
            return Response({"detail": "Payout not found"}, status=404)
        payout.status = LandlordPayout.STATUS_PAID
        payout.paid_at = timezone.now()
        payout.save(update_fields=["status", "paid_at"])
        LedgerTransaction.objects.create(
            user=payout.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
            amount=payout.amount,
            status=LedgerTransaction.STATUS_PAID,
            reference_text=f"payout:{payout.id}",
        )
        return Response({"detail": "Payout marked paid"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def landlord_revenue(request):
    if _get_role(request.user) != Profile.ROLE_LANDLORD:
        return Response({"detail": "Landlord only endpoint"}, status=403)

    period = request.GET.get("period")
    payments = PaymentTransaction.objects.filter(
        lease__unit__property__landlord=request.user,
        status=PaymentTransaction.STATUS_SUCCESS,
    )
    if period:
        payments = payments.filter(period=period)

    gross = payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    fee = gross * Decimal("0.02")
    payload = {
        "period": period,
        "gross_collected": gross,
        "fee_rate": Decimal("0.02"),
        "fee_amount": fee,
        "net_amount": gross - fee,
    }

    all_payments = PaymentTransaction.objects.filter(
        lease__unit__property__landlord=request.user,
        status=PaymentTransaction.STATUS_SUCCESS,
    )
    lifetime_gross = all_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    lifetime_fee = lifetime_gross * Decimal("0.02")
    payload["lifetime"] = {
        "gross_collected": lifetime_gross,
        "fee_amount": lifetime_fee,
        "net_amount": lifetime_gross - lifetime_fee,
    }

    return Response(LandlordRevenueSerializer(payload).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def landlord_receipts(request):
    if _get_role(request.user) != Profile.ROLE_LANDLORD:
        return Response({"detail": "Landlord only endpoint"}, status=403)

    period = request.GET.get("period")
    receipts = PaymentTransaction.objects.filter(
        lease__unit__property__landlord=request.user,
        status=PaymentTransaction.STATUS_SUCCESS,
    ).select_related("tenant", "lease", "lease__unit", "lease__unit__property").order_by("-created_at")
    if period:
        receipts = receipts.filter(period=period)
    return Response(LandlordReceiptSerializer(receipts, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def landlord_followups(request):
    if _get_role(request.user) != Profile.ROLE_LANDLORD:
        return Response({"detail": "Landlord only endpoint"}, status=403)

    period = request.GET.get("period") or timezone.localdate().strftime("%Y-%m")
    leases = Lease.objects.filter(
        status=Lease.STATUS_ACTIVE,
        unit__property__landlord=request.user,
    ).select_related("tenant", "unit", "unit__property", "tenant__profile")

    rows = []
    for lease in leases:
        rent_row = compute_lease_rent_status(lease, period=period)
        if rent_row["status"] not in ["UNPAID", "PARTIAL", "OVERDUE"]:
            continue
        tenant_profile = getattr(lease.tenant, "profile", None)
        rows.append(
            {
                "lease_id": lease.id,
                "tenant": {
                    "username": lease.tenant.username,
                    "email": lease.tenant.email,
                    "phone_number": tenant_profile.phone_number if tenant_profile else "",
                },
                "unit": {
                    "property_name": lease.unit.property.name,
                    "unit_number": lease.unit.unit_number,
                },
                "status": "PARTIAL" if rent_row["status"] == "OVERDUE" and rent_row["paid_sum"] > 0 else ("UNPAID" if rent_row["status"] == "OVERDUE" else rent_row["status"]),
                "balance": max(rent_row["balance"], Decimal("0.00")),
                "period": period,
            }
        )

    return Response(LandlordFollowupSerializer(rows, many=True).data)
