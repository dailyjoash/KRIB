import hashlib
import hmac
import json
import logging
import os
import random
import re
import uuid
from datetime import timedelta
from decimal import Decimal

try:
    import stripe
except ImportError:  # pragma: no cover - optional dependency in lightweight builds
    stripe = None
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import FileResponse, Http404
from django.db import transaction
from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils.encoding import force_bytes, force_str
from django.utils.decorators import method_decorator
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    Document,
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
    DocumentSerializer,
    LoginSerializer,
    LandlordFollowupSerializer,
    LandlordSettingsSerializer,
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
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserLiteSerializer,
    NotificationSerializer,
    NotificationSendSerializer,
    LeaseTenantContactSerializer,
    PaymentTransactionSerializer,
    PropertySerializer,
    STKInitiateSerializer,
    TenantInviteSerializer,
    TenantSerializer,
    UnitSerializer,
    WalletWithdrawSerializer,
)
from .payments import (
    apply_payment_event,
    normalize_intasend_callback,
    normalize_paypal_capture,
    normalize_stripe_event,
)
from .payments.redact import redact_payment_payload, redact_text
from .permissions import (
    IsLandlord,
    IsPropertyOwner,
    IsTenant,
    IsTenantOfProperty,
    get_role,
    landlord_has_payout_setup,
)
from .services import (
    build_public_url,
    can_withdraw_wallet,
    current_billing_period,
    current_period_string,
    execute_intasend_payout,
    intasend_stk_push,
    normalize_mpesa_phone_number,
    paypal_capture_order,
    paypal_create_order,
    period_string_to_date,
    save_payment_receipt,
    send_sms,
    unlock_due_landlord_balance,
    unlock_due_wallet_for_user,
)
from .throttles import (
    LoginRateThrottle,
    OTPRateThrottle,
    PasswordResetConfirmThrottle,
    PasswordResetRateThrottle,
    RegisterRateThrottle,
    STKInitiateRateThrottle,
    TokenObtainRateThrottle,
)

logger = logging.getLogger(__name__)
LANDLORD_HOLD_DAYS = 2
WALLET_WITHDRAW_HOLD_DAYS = 7
WALLET_CREDIT_HOLD_DAYS = 7


def _notify_users(users, title, message, *, notification_type=Notification.TYPE_GENERIC, lease=None, period=None):
    for user in users:
        if user:
            Notification.objects.create(
                user=user,
                title=title,
                message=message,
                type=notification_type,
                lease=lease,
                period=period,
            )


def _lease_tenant_phone_number(lease):
    tenant_profile = getattr(lease.tenant, "profile", None)
    return getattr(tenant_profile, "phone_number", "") or getattr(getattr(lease.tenant, "tenant_profile", None), "phone", "")


def _user_phone_number(user):
    profile = getattr(user, "profile", None)
    return getattr(profile, "phone_number", "") or getattr(getattr(user, "tenant_profile", None), "phone", "")


def _display_name(user):
    if not user:
        return ""
    return user.get_full_name() or user.username


def _generate_unique_username(full_name, email="", prefix="user"):
    cleaned_name = "".join(char.lower()
                           for char in (full_name or "") if char.isalnum())
    email_base = (email or "").split("@")[0].strip().lower()
    email_base = "".join(char for char in email_base if char.isalnum())
    username_base = cleaned_name or email_base or f"{prefix}{random.randint(1000, 9999)}"
    username = username_base
    counter = 1
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{username_base}{counter}"
    return username


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(_request):
    # Intentionally minimal: anything more leaks build/version metadata to
    # anonymous callers. The previous "debug" field told scanners whether the
    # service was running with DEBUG=1, which is a useful fingerprint for
    # attackers. Drop it.
    return Response({"status": "ok", "service": "krib-api"})


def _get_role(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile.role


def _sync_manager_account_state(user):
    if not user:
        return

    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.role != Profile.ROLE_MANAGER or user.is_staff:
        return

    should_be_active = user.managed_properties.exists()
    if user.is_active != should_be_active:
        user.is_active = should_be_active
        user.save(update_fields=["is_active"])


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "role": _get_role(user),
    }


def _current_period():
    return current_period_string()


def _tenant_active_lease(user):
    return (
        Lease.objects.filter(tenant=user, status=Lease.STATUS_ACTIVE)
        .select_related("unit", "unit__property", "tenant")
        .first()
    )


def _assert_active_lease(lease, user):
    if not lease or lease.status != Lease.STATUS_ACTIVE:
        raise DRFValidationError({"detail": "No active lease found."})
    if lease.tenant_id != user.id:
        raise PermissionDenied("Unauthorized request.")


def _validate_payment_amount(lease, amount, period):
    requested = Decimal(amount)
    if requested <= 0:
        raise DRFValidationError(
            {"detail": "Enter an amount greater than zero."})

    period_label = period.strftime(
        "%Y-%m") if hasattr(period, "strftime") else str(period)
    remaining_balance = compute_lease_rent_status(
        lease,
        period=period_label,
        today=timezone.localdate(),
    ).get("balance", Decimal("0.00"))

    if remaining_balance <= 0:
        raise DRFValidationError(
            {"detail": "Rent for this period is already fully paid."})

    if requested > remaining_balance:
        raise DRFValidationError(
            {"detail": f"Amount cannot exceed the remaining balance of Ksh {remaining_balance:.2f}."}
        )


def _user_can_access_document(user, document):
    role = _get_role(user)
    if user.is_staff:
        return True
    if role == Profile.ROLE_LANDLORD and document.property.landlord_id == user.id:
        return True
    if role == Profile.ROLE_MANAGER and document.property.manager_id == user.id:
        return True
    if role == Profile.ROLE_TENANT:
        # A tenant can only view documents that explicitly target them.
        # Property-wide visibility (lease/other documents owned by the
        # landlord) is intentionally not granted here.
        if document.tenant_id == user.id:
            return True
        if document.lease_id and document.lease.tenant_id == user.id:
            return True
        return False
    return False


def _user_can_access_payment_receipt(user, payment):
    role = _get_role(user)
    if role == Profile.ROLE_TENANT and payment.tenant_id == user.id:
        return True
    if role == Profile.ROLE_LANDLORD and payment.lease.unit.property.landlord_id == user.id:
        return True
    return False


def _scoped_properties(user):
    role = _get_role(user)
    if role == Profile.ROLE_LANDLORD:
        return Property.objects.filter(landlord=user)
    if role == Profile.ROLE_MANAGER:
        return Property.objects.filter(manager=user)
    if role == Profile.ROLE_TENANT:
        return Property.objects.filter(units__leases__tenant=user, units__leases__status=Lease.STATUS_ACTIVE).distinct()
    return Property.objects.none()


def _notification_recipients(user, audience, property_obj=None):
    role = _get_role(user)
    if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not user.is_staff:
        raise PermissionDenied(
            "Only landlord or manager can send notifications.")

    if user.is_staff:
        scoped_properties = Property.objects.all()
    elif role == Profile.ROLE_MANAGER:
        scoped_properties = Property.objects.filter(manager=user)
    else:
        scoped_properties = Property.objects.filter(landlord=user)

    if property_obj is not None:
        if not user.is_staff and not scoped_properties.filter(pk=property_obj.pk).exists():
            raise PermissionDenied(
                "You can only notify users in your own portfolio.")
        scoped_properties = Property.objects.filter(pk=property_obj.pk)

    tenants = User.objects.filter(profile__role=Profile.ROLE_TENANT)
    managers = User.objects.filter(profile__role=Profile.ROLE_MANAGER)
    landlords = User.objects.filter(profile__role=Profile.ROLE_LANDLORD)

    if not user.is_staff or property_obj is not None:
        tenants = tenants.filter(
            leases__unit__property__in=scoped_properties,
            leases__status=Lease.STATUS_ACTIVE,
        )
        managers = managers.filter(managed_properties__in=scoped_properties)
        landlords = landlords.filter(properties__in=scoped_properties)

    if audience == NotificationSendSerializer.AUDIENCE_TENANTS:
        recipients = tenants
    elif audience == NotificationSendSerializer.AUDIENCE_MANAGERS:
        recipients = managers
    elif audience == NotificationSendSerializer.AUDIENCE_LANDLORDS:
        if not user.is_staff:
            raise PermissionDenied("Only staff can notify landlords.")
        recipients = landlords
    else:
        recipients = tenants | managers
        if user.is_staff:
            recipients = recipients | landlords

    return recipients.exclude(pk=user.pk).distinct()


def _require_landlord_or_staff(user):
    if _get_role(user) != Profile.ROLE_LANDLORD and not user.is_staff:
        raise PermissionDenied("Only landlord can modify properties")


def _unlock_wallet(profile):
    """Backwards-compatible shim around the safe service.

    The previous implementation aggregated and updated rows without row locks,
    which let two concurrent requests double-credit the same locked ledger
    rows. All call sites now route through services.unlock_due_wallet_for_user
    which processes one row at a time inside select_for_update.
    """
    if not profile:
        return
    unlock_due_wallet_for_user(profile.user)
    # Refresh in-memory profile so the caller sees the new balances. The view
    # layer reads these fields right after calling us.
    profile.refresh_from_db(fields=["wallet_locked", "wallet_available", "updated_at"])


def _unlock_landlord(balance):
    """Backwards-compatible shim around the safe service."""
    if not balance:
        return
    unlock_due_landlord_balance(balance.landlord)
    balance.refresh_from_db(fields=["locked_balance", "available_balance", "updated_at"])


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
    _notify_users(
        [lease.tenant, landlord],
        "Wallet rent applied",
        f"KES {debit} from the tenant wallet has been applied to {lease.unit.property.name} / {lease.unit.unit_number}.",
        lease=lease,
        period=period,
    )
    return debit


def _wallet_aware_rent_status(lease, rent_status, wallet_available, *, today=None):
    # Dashboard reads should reflect the balance-based wallet model without
    # creating payment rows or mutating ledger balances on a GET request.
    today = today or timezone.localdate()
    adjusted = dict(rent_status or {})
    available_wallet = max(
        Decimal(wallet_available or Decimal("0.00")), Decimal("0.00"))
    raw_balance = max(Decimal(adjusted.get("balance")
                      or Decimal("0.00")), Decimal("0.00"))

    if available_wallet <= 0 or raw_balance <= 0:
        return adjusted

    carried_forward_balance = max(
        Decimal(adjusted.get("carried_forward_balance") or Decimal("0.00")),
        Decimal("0.00"),
    )
    current_period_balance = max(
        Decimal(adjusted.get("current_period_balance") or Decimal("0.00")),
        Decimal("0.00"),
    )
    wallet_applied = min(available_wallet, raw_balance)
    wallet_applied_to_arrears = min(wallet_applied, carried_forward_balance)
    wallet_applied_to_current = min(
        wallet_applied - wallet_applied_to_arrears, current_period_balance)

    adjusted["carried_forward_balance"] = carried_forward_balance - \
        wallet_applied_to_arrears
    adjusted["current_period_balance"] = current_period_balance - \
        wallet_applied_to_current
    adjusted["balance"] = raw_balance - wallet_applied

    if adjusted["balance"] <= 0:
        adjusted["status"] = "PAID"
    elif adjusted["carried_forward_balance"] > 0:
        adjusted["status"] = "OVERDUE"
    elif adjusted["current_period_balance"] > 0 and today.day > lease.due_day:
        adjusted["status"] = "OVERDUE"
    elif adjusted.get("paid_sum", Decimal("0.00")) > 0 or wallet_applied > 0:
        adjusted["status"] = "PARTIAL"
    else:
        adjusted["status"] = "UNPAID"

    return adjusted


def _allocate_success_payment(payment):
    payment_id = getattr(payment, "pk", None)
    if not payment_id:
        return

    notification_context = None

    with transaction.atomic():
        locked_payment = (
            PaymentTransaction.objects.select_for_update()
            .select_related("lease", "lease__unit", "lease__unit__property", "tenant")
            .get(pk=payment_id)
        )
        if locked_payment.allocation_done or locked_payment.status != PaymentTransaction.STATUS_SUCCESS:
            return

        lease = Lease.objects.select_for_update().select_related(
            "unit", "unit__property").get(pk=locked_payment.lease_id)
        landlord = lease.unit.property.landlord

        profile, _ = Profile.objects.get_or_create(user=locked_payment.tenant)
        profile = Profile.objects.select_for_update().get(pk=profile.pk)

        landlord_balance, _ = LandlordBalance.objects.get_or_create(
            landlord=landlord)
        landlord_balance = LandlordBalance.objects.select_for_update().get(
            pk=landlord_balance.pk)

        # Serialize allocations per lease and compute the outstanding rent from
        # already-applied landlord credits, not from potentially concurrent
        # successful payments that have not been allocated yet.
        target_month = (locked_payment.billing_period or period_string_to_date(
            locked_payment.period)).replace(day=1)
        lease_start_month = lease.start_date.replace(day=1)
        lease_end_month = lease.end_date.replace(
            day=1) if lease.end_date else target_month
        effective_end_month = min(target_month, lease_end_month)

        if effective_end_month < lease_start_month:
            cumulative_rent_due = Decimal("0.00")
        else:
            billable_months = ((effective_end_month.year - lease_start_month.year) * 12) + (
                effective_end_month.month - lease_start_month.month
            ) + 1
            cumulative_rent_due = lease.rent_amount * billable_months

        already_applied = (
            LedgerTransaction.objects.filter(
                user=landlord,
                kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
            )
            .filter(
                Q(reference_text__contains=f";lease:{lease.id}")
                | Q(reference_text=f"wallet_debit_lease:{lease.id}")
            )
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        remaining_due_before_payment = max(
            cumulative_rent_due - already_applied, Decimal("0.00"))
        rent_applied = min(locked_payment.amount, remaining_due_before_payment)
        overpayment = locked_payment.amount - rent_applied

        if rent_applied > 0:
            landlord_balance.locked_balance += rent_applied
            landlord_balance.save(
                update_fields=["locked_balance", "updated_at"])
            LedgerTransaction.objects.create(
                user=landlord,
                kind=LedgerTransaction.KIND_LANDLORD_CREDIT_RENT,
                amount=rent_applied,
                status=LedgerTransaction.STATUS_LOCKED,
                available_at=timezone.now() + timedelta(days=LANDLORD_HOLD_DAYS),
                reference_text=f"payment:{locked_payment.id};lease:{lease.id}",
            )

        if overpayment > 0:
            profile.wallet_locked += overpayment
            profile.save(update_fields=["wallet_locked", "updated_at"])
            LedgerTransaction.objects.create(
                user=locked_payment.tenant,
                kind=LedgerTransaction.KIND_WALLET_CREDIT,
                amount=overpayment,
                status=LedgerTransaction.STATUS_LOCKED,
                available_at=timezone.now() + timedelta(days=WALLET_CREDIT_HOLD_DAYS),
                reference_text=f"payment:{locked_payment.id};lease:{lease.id}",
            )

        locked_payment.allocation_done = True
        locked_payment.save(update_fields=["allocation_done"])
        notification_context = (locked_payment.tenant, landlord,
                                lease, locked_payment.amount, locked_payment.period)

    tenant, landlord, lease, amount, period = notification_context
    _notify_users(
        [tenant, landlord],
        "Rent payment received",
        f"Rent payment of KES {amount} for {period} was processed successfully for {lease.unit.property.name} / {lease.unit.unit_number}.",
        lease=lease,
        period=period,
    )


def _missing_intasend_env_vars():
    required_vars = [
        "INTASEND_API_TOKEN",
        "INTASEND_PUBLISHABLE_KEY",
        "INTASEND_TEST_MODE",
    ]
    return [name for name in required_vars if not os.getenv(name)]


def _verify_intasend_signature(raw_body, signature):
    secret = os.getenv("INTASEND_WEBHOOK_SECRET", "").strip()
    if not secret or not signature:
        return False

    expected_signature = hmac.new(
        secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_signature, signature.strip())


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def get_me(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response(
            {
                "id": request.user.id,
                "username": _display_name(request.user),
                "full_name": _display_name(request.user),
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "role": profile.role,
                "is_staff": request.user.is_staff,
                "email": request.user.email,
                "phone_number": profile.phone_number,
            }
        )

    serializer = MeSerializer(data=request.data, partial=True, context={"request": request})
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data.get("email")
    phone_number = serializer.validated_data.get("phone_number")
    if email is not None:
        # Normalize before persisting so the uniqueness check at the
        # serializer layer and the stored value cannot drift apart.
        request.user.email = email.strip().lower()
        request.user.save(update_fields=["email"])
    if phone_number is not None:
        profile.phone_number = phone_number
        profile.save(update_fields=["phone_number"])

    return Response(
        {
            "id": request.user.id,
            "username": _display_name(request.user),
            "full_name": _display_name(request.user),
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "role": profile.role,
            "is_staff": request.user.is_staff,
            "email": request.user.email,
            "phone_number": profile.phone_number,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    name = serializer.validated_data["name"].strip()
    email = serializer.validated_data["email"].strip().lower()
    phone = serializer.validated_data.get("phone", "").strip()
    role = serializer.validated_data["role"]

    # Account-enumeration mitigation: return the same neutral payload whether
    # the email is in use or not. The legitimate owner of the address gets a
    # heads-up email; the caller learns nothing.
    if User.objects.filter(email__iexact=email).exists():
        existing = User.objects.filter(email__iexact=email).first()
        try:
            send_mail(
                subject="KRIB account exists",
                message=(
                    "Someone tried to create a new KRIB account using this email. "
                    "If that was you, sign in with your existing credentials or "
                    "use the password reset link from the login page."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[existing.email],
                fail_silently=True,
            )
        except Exception:  # pragma: no cover - defensive when SMTP is unconfigured
            logger.exception("Failed to send 'account exists' notice.")
        return Response({"detail": "Registration submitted."}, status=202)

    with transaction.atomic():
        username = _generate_unique_username(name, email=email)
        user = User.objects.create(
            username=username, email=email, first_name=name)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = role
        profile.phone_number = phone
        profile.save(update_fields=["role", "phone_number"])

        tenant_profile, _ = Tenant.objects.get_or_create(user=user)
        if role == Profile.ROLE_TENANT:
            tenant_profile.phone = phone
            tenant_profile.save(update_fields=["phone"])

    return Response(
        {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.first_name or user.username,
                "phone": profile.phone_number,
                "role": profile.role,
                "is_staff": user.is_staff,
            },
            **_issue_tokens(user),
        },
        status=201,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    identifier = serializer.validated_data["email"].strip()
    password = serializer.validated_data["password"]
    user = User.objects.filter(email__iexact=identifier).first()
    if not user:
        user = User.objects.filter(username__iexact=identifier).first()
    if not user:
        return Response({"detail": "Invalid login details."}, status=400)

    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.role == Profile.ROLE_MANAGER and not user.is_staff and not user.is_active:
        return Response({"detail": "This manager account is inactive until a property is assigned."}, status=403)

    authenticated = authenticate(username=user.username, password=password)
    if not authenticated:
        return Response({"detail": "Invalid login details."}, status=400)

    profile, _ = Profile.objects.get_or_create(user=authenticated)
    return Response(
        {
            "user": {
                "id": authenticated.id,
                "email": authenticated.email,
                "name": authenticated.first_name or authenticated.username,
                "phone": profile.phone_number,
                "role": profile.role,
                "is_staff": authenticated.is_staff,
            },
            **_issue_tokens(authenticated),
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def signup_landlord(request):
    serializer = LandlordSignupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    first_name = serializer.validated_data["first_name"].strip()
    last_name = serializer.validated_data["last_name"].strip()
    email = (serializer.validated_data.get("email", "") or "").strip().lower()

    # Same neutral-response pattern as /api/auth/register/. We must never
    # reveal whether an email is already in use, otherwise this endpoint
    # becomes an account-enumeration oracle.
    if email and User.objects.filter(email__iexact=email).exists():
        existing = User.objects.filter(email__iexact=email).first()
        try:
            send_mail(
                subject="KRIB account exists",
                message=(
                    "Someone tried to create a new KRIB landlord account using this email. "
                    "If that was you, sign in with your existing credentials or use the "
                    "password reset link from the login page."
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[existing.email],
                fail_silently=True,
            )
        except Exception:  # pragma: no cover
            logger.exception("Failed to send 'account exists' notice (landlord).")
        return Response({"detail": "Landlord signup submitted."}, status=202)

    with transaction.atomic():
        full_name = f"{first_name} {last_name}".strip()
        user = User.objects.create(
            username=_generate_unique_username(full_name, email=email),
            email=email,
            first_name=first_name,
            last_name=last_name,
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


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRateThrottle])
def password_reset_request(request):
    serializer = PasswordResetRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"].strip().lower()
    user = User.objects.filter(email__iexact=email).first()

    if user:
        frontend_base = settings.FRONTEND_URL or "http://localhost:5173"
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = f"{frontend_base.rstrip('/')}/reset-password/{uid}/{token}"
        send_mail(
            subject="KRIB password reset",
            message=f"Use this link to reset your KRIB password: {reset_link}",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[user.email],
            fail_silently=True,
        )

    return Response({"detail": "If that email exists, a password reset link has been sent."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetConfirmThrottle])
def password_reset_confirm(request):
    serializer = PasswordResetConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        user_id = force_str(urlsafe_base64_decode(
            serializer.validated_data["uid"]))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"detail": "Invalid reset link."}, status=400)

    if not default_token_generator.check_token(user, serializer.validated_data["token"]):
        return Response({"detail": "Invalid or expired reset link."}, status=400)

    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])
    return Response({"detail": "Password reset successfully."})


def _frontend_base_url():
    return (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")


def _can_send_email():
    backend = getattr(settings, "EMAIL_BACKEND", "")
    return bool(
        backend
        and (
            backend != "django.core.mail.backends.smtp.EmailBackend"
            or getattr(settings, "EMAIL_HOST", "")
        )
    )


def _send_invite_channels(*, subject, email_message, sms_message, email=None, phone=None):
    email_sent = False
    sms_sent = False

    if email and _can_send_email():
        send_mail(
            subject=subject,
            message=email_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=True,
        )
        email_sent = True

    if phone:
        sms_sent = send_sms(phone, sms_message)

    return {"email_sent": email_sent, "sms_sent": sms_sent}


def _manager_invite_link(invite):
    return f"{_frontend_base_url()}/invite/manager/{invite.token}"


def _tenant_invite_link(invite):
    return f"{_frontend_base_url()}/invite/tenant/{invite.token}"


def send_manager_invite(invite, display_name=""):
    invite_link = _manager_invite_link(invite)
    name = (display_name or "there").strip()
    delivery = _send_invite_channels(
        subject="KRIB Manager Invite",
        email_message=(
            f"Hello {name},\n\n"
            f"You have been invited to join KRIB as a manager.\n"
            f"Use this first-login link to create your account: {invite_link}"
        ),
        sms_message=(
            f"KRIB manager invite for {name or 'you'}. "
            f"Create your account here: {invite_link}"
        ),
        email=invite.email,
        phone=invite.phone,
    )
    return {"invite_link": invite_link, **delivery}


def send_tenant_invite(invite):
    invite_link = _tenant_invite_link(invite)
    unit_label = invite.unit.unit_number if invite.unit else ""
    property_name = invite.property.name if invite.property else ""
    location_bits = " / ".join(
        bit for bit in [property_name, unit_label] if bit)
    context = f" for {location_bits}" if location_bits else ""
    delivery = _send_invite_channels(
        subject="KRIB Tenant Invite",
        email_message=(
            f"Hello {invite.full_name},\n\n"
            f"You have been invited to KRIB{context}.\n"
            f"Use this first-login link to create your tenant account: {invite_link}"
        ),
        sms_message=(
            f"KRIB tenant invite{context}. "
            f"Create your account here: {invite_link}"
        ),
        email=invite.email,
        phone=invite.phone,
    )
    return {"invite_link": invite_link, **delivery}


class ManagerInviteCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        role = get_role(request.user)
        if role != Profile.ROLE_LANDLORD and not request.user.is_staff:
            return Response({"detail": "Only landlord/admin can create manager invites."}, status=403)
        # The frontend disables the CTA for UX, but the backend must still enforce
        # the rule so direct API calls cannot bypass payout setup requirements.
        if not request.user.is_staff and not landlord_has_payout_setup(request.user):
            return Response(
                {
                    "detail": "Set up your payment method before inviting a manager.",
                    "code": "payout_not_configured",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
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
        delivery = send_manager_invite(invite, request.data.get("name", ""))
        return Response(
            {
                "token": str(invite.token),
                "expires_at": invite.expires_at,
                **delivery,
            },
            status=201,
        )


class ManagerInviteAcceptView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ManagerInviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = ManagerInvite.objects.filter(
            token=serializer.validated_data["token"], is_active=True).first()
        if not invite:
            return Response({"detail": "Invalid invite token."}, status=400)
        if invite.is_expired() or invite.accepted_at:
            return Response({"detail": "Invite expired or already used."}, status=400)

        first_name = serializer.validated_data["first_name"].strip()
        last_name = serializer.validated_data["last_name"].strip()
        full_name = f"{first_name} {last_name}".strip()
        username = _generate_unique_username(
            full_name, email=invite.email or "", prefix="manager")
        user = User.objects.create(
            username=username,
            email=invite.email or "",
            first_name=first_name,
            last_name=last_name,
        )
        created = True
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
    serializer_class = UserLiteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Staff/admin keeps full visibility. Everyone else only sees users
        # they have a legitimate relationship with — same scoping logic as
        # TenantViewSet/PropertySerializer's manager_id field. Previously this
        # leaked every tenant/landlord/manager email on the platform to any
        # authenticated landlord.
        request_user = self.request.user
        if request_user.is_staff:
            base = User.objects.all().order_by("id")
            role = self.request.query_params.get("role")
            if role in dict(Profile.ROLE_CHOICES):
                base = base.filter(profile__role=role)
            return base

        role = self.request.query_params.get("role")
        if role not in dict(Profile.ROLE_CHOICES):
            return User.objects.none()

        requester_role = _get_role(request_user)

        if requester_role == Profile.ROLE_TENANT:
            # Tenants see themselves only when asking about their own role;
            # all other roles return an empty list so a tenant cannot use
            # /api/users/?role=manager as a back-channel into the manager pool.
            if role == Profile.ROLE_TENANT:
                return User.objects.filter(pk=request_user.pk)
            return User.objects.none()

        if requester_role == Profile.ROLE_MANAGER:
            scoped_properties = Property.objects.filter(manager=request_user)
        elif requester_role == Profile.ROLE_LANDLORD:
            scoped_properties = Property.objects.filter(landlord=request_user)
        else:
            return User.objects.none()

        if role == Profile.ROLE_TENANT:
            invite_emails = list(
                TenantInvite.objects.filter(
                    invited_by=request_user,
                    status=TenantInvite.STATUS_ACCEPTED,
                )
                .exclude(email__isnull=True).exclude(email__exact="")
                .values_list("email", flat=True)
            )
            invite_phones = list(
                TenantInvite.objects.filter(
                    invited_by=request_user,
                    status=TenantInvite.STATUS_ACCEPTED,
                )
                .exclude(phone__isnull=True).exclude(phone__exact="")
                .values_list("phone", flat=True)
            )
            filters = Q(leases__unit__property__in=scoped_properties)
            if invite_emails:
                filters |= Q(email__in=invite_emails)
            if invite_phones:
                filters |= Q(profile__phone_number__in=invite_phones) | Q(
                    tenant_profile__phone__in=invite_phones
                )
            return User.objects.filter(profile__role=role).filter(filters).distinct().order_by("id")

        if role == Profile.ROLE_MANAGER:
            # Managers visible to a landlord: those already on one of their
            # properties OR managers who accepted an invite this landlord sent.
            invites = ManagerInvite.objects.filter(
                created_by=request_user,
                accepted_at__isnull=False,
            )
            invite_emails = list(
                invites.exclude(email__isnull=True).exclude(email__exact="")
                .values_list("email", flat=True)
            )
            invite_phones = list(
                invites.exclude(phone__isnull=True).exclude(phone__exact="")
                .values_list("phone", flat=True)
            )
            filters = Q(managed_properties__in=scoped_properties)
            if invite_emails:
                filters |= Q(email__in=invite_emails)
            if invite_phones:
                filters |= Q(profile__phone_number__in=invite_phones)
            return User.objects.filter(profile__role=role).filter(filters).distinct().order_by("id")

        if role == Profile.ROLE_LANDLORD:
            # Non-staff has no legitimate reason to enumerate landlords.
            return User.objects.none()

        return User.objects.none()


class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _scoped_properties(self.request.user).order_by("id")

    def perform_create(self, serializer):
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord can create properties")
        property_row = serializer.save(landlord=self.request.user)
        _sync_manager_account_state(property_row.manager)

    def perform_update(self, serializer):
        _require_landlord_or_staff(self.request.user)
        previous_manager = serializer.instance.manager
        property_row = serializer.save()
        manager_candidates = []
        for manager in [previous_manager, property_row.manager]:
            if manager and all(existing.id != manager.id for existing in manager_candidates):
                manager_candidates.append(manager)
        for manager in manager_candidates:
            _sync_manager_account_state(manager)

    def perform_destroy(self, instance):
        _require_landlord_or_staff(self.request.user)
        previous_manager = instance.manager
        instance.delete()
        _sync_manager_account_state(previous_manager)


class UnitViewSet(viewsets.ModelViewSet):
    serializer_class = UnitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        props = _scoped_properties(self.request.user)
        return Unit.objects.filter(property__in=props).select_related("property").order_by("id")

    def perform_create(self, serializer):
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord/manager can create units")

        unit_property = serializer.validated_data["property"]
        if unit_property not in _scoped_properties(self.request.user):
            raise PermissionDenied(
                "Cannot create units outside your assigned properties")

        serializer.save()

    def perform_update(self, serializer):
        # Re-run the create-time scope check. Without this a landlord could
        # PATCH `property_id` to a property they do not own (since DRF's
        # default scoping only filters reads, not the writable FK target).
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord/manager can update units")
        target_property = serializer.validated_data.get("property", serializer.instance.property)
        if target_property not in _scoped_properties(self.request.user):
            raise PermissionDenied("Cannot move a unit outside your assigned properties")
        serializer.save()

    def perform_destroy(self, instance):
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord can delete units")
        if instance.property not in _scoped_properties(self.request.user):
            raise PermissionDenied("Cannot delete units outside your portfolio")
        instance.delete()


class LeaseViewSet(viewsets.ModelViewSet):
    serializer_class = LeaseSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == Profile.ROLE_TENANT:
            return Lease.objects.filter(tenant=user).select_related("unit", "unit__property", "tenant").order_by("unit__property__name", "unit__unit_number", "id")
        return Lease.objects.filter(unit__property__in=_scoped_properties(user)).select_related("unit", "unit__property", "tenant").order_by("unit__property__name", "unit__unit_number", "id")

    def perform_create(self, serializer):
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord/manager can create leases")

        lease_unit = serializer.validated_data["unit"]
        if lease_unit.property not in _scoped_properties(self.request.user):
            raise PermissionDenied(
                "Cannot create leases outside your assigned properties")

        lease = serializer.save()
        self._lease_post_create(lease)

    def perform_update(self, serializer):
        # Guard PATCH on /api/leases/<id>/ so a landlord cannot retarget an
        # owned lease at a unit they do not own.
        role = _get_role(self.request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not self.request.user.is_staff:
            raise PermissionDenied("Only landlord/manager can update leases")
        target_unit = serializer.validated_data.get("unit", serializer.instance.unit)
        if target_unit.property not in _scoped_properties(self.request.user):
            raise PermissionDenied("Cannot move a lease outside your assigned properties")
        serializer.save()

    def _lease_post_create(self, lease):
        login_link = (
            settings.FRONTEND_URL or "http://localhost:5173").rstrip("/") + "/login"
        phone_number = _lease_tenant_phone_number(lease)
        tenant_name = lease.tenant.get_full_name() or lease.tenant.username
        property_label = f"{lease.unit.property.name} / {lease.unit.unit_number}"

        _notify_users(
            [lease.tenant],
            "Lease documents ready",
            f"Your lease for {property_label} is active. Open Documents in KRIB to review your signed agreement and identification record.",
            lease=lease,
        )

        if lease.tenant.email:
            send_mail(
                "KRIB lease documents ready",
                (
                    f"Hello {tenant_name},\n\n"
                    f"Your lease for {property_label} is now active in KRIB.\n"
                    f"Your signed tenant agreement and identification document are available in the Documents tab.\n"
                    f"Sign in here: {login_link}\n"
                ),
                settings.DEFAULT_FROM_EMAIL or None,
                [lease.tenant.email],
                fail_silently=True,
            )
        if phone_number:
            send_sms(
                phone_number,
                f"Your KRIB lease for {property_label} is active. Your signed agreement is ready in Documents. Log in here: {login_link}",
            )

    @action(detail=True, methods=["post"], url_path="contact-tenant")
    def contact_tenant(self, request, pk=None):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not request.user.is_staff:
            return Response({"detail": "Unauthorized request."}, status=403)

        lease = self.get_object()
        serializer = LeaseTenantContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        channel = serializer.validated_data["channel"]
        subject = (serializer.validated_data.get("subject") or "").strip()
        message = serializer.validated_data["message"].strip()
        default_subject = subject or f"KRIB update for {lease.unit.property.name} / {lease.unit.unit_number}"

        if channel == LeaseTenantContactSerializer.CHANNEL_EMAIL:
            if not lease.tenant.email:
                return Response({"detail": "This tenant does not have an email address."}, status=400)
            try:
                send_mail(
                    default_subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL or None,
                    [lease.tenant.email],
                    fail_silently=False,
                )
            except Exception as exc:  # pragma: no cover - depends on env transport
                logger.warning("Email delivery failed: %s", exc)
                return Response({"detail": "Email delivery failed. Check your SMTP configuration."}, status=503)
            delivery_label = "Email sent to tenant."
        else:
            phone_number = _lease_tenant_phone_number(lease)
            if not phone_number:
                return Response({"detail": "This tenant does not have a phone number."}, status=400)
            sms_result = send_sms(phone_number, message, include_detail=True)
            sms_ok = sms_result if isinstance(
                sms_result, bool) else sms_result.get("ok")
            sms_detail = "" if isinstance(
                sms_result, bool) else sms_result.get("detail")
            if not sms_ok:
                return Response(
                    {
                        "detail": sms_detail
                        or "SMS delivery failed. Check the Africa's Talking sandbox setup."
                    },
                    status=503,
                )
            delivery_label = "SMS sent to tenant."

        _notify_users([lease.tenant], default_subject, message, lease=lease)
        return Response({"detail": delivery_label})

    @action(detail=True, methods=["post"], url_path="remove-tenant")
    def remove_tenant(self, request, pk=None):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and not request.user.is_staff:
            return Response({"detail": "Unauthorized request."}, status=403)

        lease = self.get_object()
        if lease.status != Lease.STATUS_ACTIVE:
            return Response({"detail": "Only active leases can be ended."}, status=400)

        today = timezone.localdate()
        if not lease.end_date or lease.end_date > today:
            lease.end_date = today
        lease.status = Lease.STATUS_INACTIVE
        lease.save()

        tenant_name = lease.tenant.get_full_name() or lease.tenant.username
        property_label = f"{lease.unit.property.name} / {lease.unit.unit_number}"
        _notify_users(
            [lease.tenant],
            "Lease ended",
            f"Your lease for {property_label} has been ended in KRIB. Contact the landlord or manager if you need any clarification.",
            lease=lease,
        )

        if lease.tenant.email:
            send_mail(
                "KRIB lease ended",
                (
                    f"Hello {tenant_name},\n\n"
                    f"Your lease for {property_label} has been ended in KRIB.\n"
                    "Contact your landlord or manager if this needs follow-up.\n"
                ),
                settings.DEFAULT_FROM_EMAIL or None,
                [lease.tenant.email],
                fail_silently=True,
            )

        phone_number = _lease_tenant_phone_number(lease)
        if phone_number:
            send_sms(
                phone_number,
                f"Your KRIB lease for {property_label} has been ended. Contact the landlord or manager if you have any questions.",
            )

        return Response({"detail": "Tenant removed from the unit.", "lease": LeaseSerializer(lease).data})


class InviteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = TenantInvite.objects.all().order_by("-id")
    serializer_class = TenantInviteSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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

    def retrieve(self, request, *args, **kwargs):
        invite = TenantInvite.objects.filter(token=kwargs.get("pk")).select_related(
            "property", "unit__property", "invited_by").first()
        if not invite:
            return Response({"detail": "Tenant invite not found."}, status=404)
        if invite.is_expired() and invite.status == TenantInvite.STATUS_PENDING:
            invite.status = TenantInvite.STATUS_EXPIRED
            invite.save(update_fields=["status"])
        return Response(TenantInviteSerializer(invite).data)

    def create(self, request, *args, **kwargs):
        role = get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Response({"detail": "Only landlord/manager can invite."}, status=403)
        # The client-side warning prevents a confusing dead-end, but security has
        # to live here because API consumers can bypass the React app entirely.
        if role == Profile.ROLE_LANDLORD and not landlord_has_payout_setup(request.user):
            return Response(
                {
                    "detail": "Set up your payment method before inviting tenants.",
                    "code": "payout_not_configured",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save(invited_by=request.user)
        if role == Profile.ROLE_MANAGER and invite.property and invite.property.manager != request.user:
            invite.delete()
            return Response({"detail": "Managers can only invite for assigned properties."}, status=403)
        data = TenantInviteSerializer(invite).data
        data.update(send_tenant_invite(invite))
        return Response(data, status=201)

    @action(detail=True, methods=["post"], url_path="resend")
    def resend(self, request, pk=None):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Response({"detail": "Only landlord or manager can resend invites."}, status=403)

        invite = self.get_object()
        if invite.status != TenantInvite.STATUS_PENDING:
            return Response({"detail": "Only pending tenant invites can be resent."}, status=400)
        if invite.is_expired():
            invite.status = TenantInvite.STATUS_EXPIRED
            invite.save(update_fields=["status"])
            return Response({"detail": "This tenant invite has expired. Create a fresh invite instead."}, status=400)

        data = TenantInviteSerializer(invite).data
        data.update(send_tenant_invite(invite))
        return Response(data, status=200)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        role = _get_role(request.user)
        if role not in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER]:
            return Response({"detail": "Only landlord or manager can cancel invites."}, status=403)

        invite = self.get_object()
        if invite.status != TenantInvite.STATUS_PENDING:
            return Response({"detail": "Only pending tenant invites can be cancelled."}, status=400)

        invite.status = TenantInvite.STATUS_CANCELLED
        invite.save(update_fields=["status"])
        return Response({"detail": "Tenant invite cancelled.", "status": invite.status}, status=200)

    @action(detail=True, methods=["post"], url_path="verify-otp", throttle_classes=[OTPRateThrottle])
    def verify_otp(self, request, pk=None):
        invite = TenantInvite.objects.filter(token=pk).first()
        if not invite:
            return Response({"detail": "Tenant invite not found."}, status=404)
        if not invite.otp_code:
            return Response({"detail": "OTP not enabled for this invite."}, status=400)
        if invite.otp_expires_at and timezone.now() > invite.otp_expires_at:
            return Response({"detail": "OTP expired."}, status=400)

        if invite.otp_locked:
            return Response(
                {"detail": "Too many failed attempts. Request a new invite."},
                status=429,
            )

        TenantInvite.objects.filter(pk=invite.pk).update(
            otp_attempts=F("otp_attempts") + 1
        )
        invite.refresh_from_db()

        if invite.otp_attempts > 5:
            invite.otp_locked = True
            invite.save(update_fields=["otp_locked"])
            return Response(
                {"detail": "Too many failed attempts. Request a new invite."},
                status=429,
            )

        submitted_otp = (request.data.get("otp_code") or "").strip()
        if not submitted_otp or submitted_otp != invite.otp_code:
            return Response({"detail": "Invalid OTP."}, status=400)

        invite.otp_attempts = 0
        invite.save(update_fields=["otp_attempts"])
        return Response({"detail": "OTP verified."})

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        serializer = InviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submitted_otp = (request.data.get("otp_code") or "").strip()
        first_name = serializer.validated_data["first_name"].strip()
        last_name = serializer.validated_data["last_name"].strip()

        # The whole acceptance happens under select_for_update so two
        # concurrent acceptances of the same invite cannot both win.
        with transaction.atomic():
            invite = (
                TenantInvite.objects.select_for_update()
                .filter(token=pk)
                .first()
            )
            if not invite:
                return Response({"detail": "Tenant invite not found."}, status=404)
            if invite.is_expired():
                if invite.status == TenantInvite.STATUS_PENDING:
                    invite.status = TenantInvite.STATUS_EXPIRED
                    invite.save(update_fields=["status"])
                return Response({"detail": "This tenant invite has expired."}, status=400)
            if invite.status == TenantInvite.STATUS_CANCELLED:
                return Response({"detail": "This tenant invite was cancelled."}, status=400)
            if invite.status == TenantInvite.STATUS_ACCEPTED:
                return Response({"detail": "This tenant invite has already been used."}, status=400)
            if invite.status != TenantInvite.STATUS_PENDING:
                return Response({"detail": "This tenant invite is no longer active."}, status=400)

            # OTP gate: if the inviter set an OTP on the invite, the caller
            # MUST submit it and it MUST match. Without this check anyone with
            # the invite token (e.g. via email/SMS sniffing) could accept.
            if invite.otp_code:
                if invite.otp_locked:
                    return Response(
                        {"detail": "Too many failed attempts. Request a new invite."},
                        status=429,
                    )
                if invite.otp_expires_at and timezone.now() > invite.otp_expires_at:
                    return Response({"detail": "OTP expired."}, status=400)
                if not submitted_otp:
                    return Response({"detail": "OTP is required to accept this invite.", "code": "otp_required"}, status=400)
                if submitted_otp != invite.otp_code:
                    invite.otp_attempts = (invite.otp_attempts or 0) + 1
                    if invite.otp_attempts > 5:
                        invite.otp_locked = True
                        invite.save(update_fields=["otp_attempts", "otp_locked"])
                        return Response(
                            {"detail": "Too many failed attempts. Request a new invite."},
                            status=429,
                        )
                    invite.save(update_fields=["otp_attempts"])
                    return Response({"detail": "Invalid OTP."}, status=400)

            full_name = f"{first_name} {last_name}".strip()
            username = _generate_unique_username(
                full_name, email=invite.email or "", prefix="tenant")

            user = User.objects.create(
                username=username,
                email=(invite.email or "").lower(),
                first_name=first_name,
                last_name=last_name,
            )
            user.set_password(serializer.validated_data["password"])
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = Profile.ROLE_TENANT
            if invite.phone:
                profile.phone_number = invite.phone
                profile.save(update_fields=["role", "phone_number"])
            else:
                profile.save(update_fields=["role"])
            tenant_profile, _ = Tenant.objects.get_or_create(user=user)
            if invite.phone:
                tenant_profile.phone = invite.phone
                tenant_profile.save(update_fields=["phone"])
            invite.status = TenantInvite.STATUS_ACCEPTED
            invite.otp_attempts = 0
            invite.save(update_fields=["status", "otp_attempts"])
        return Response({"detail": "Invite accepted.", "name": _display_name(user), "created": True})


class LandlordSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_settings(self, user):
        defaults = {"business_name": user.get_full_name().strip()
                    or user.username}
        settings_obj, _ = LandlordSettings.objects.get_or_create(
            user=user, defaults=defaults)
        return settings_obj

    def get(self, request):
        if get_role(request.user) != Profile.ROLE_LANDLORD and not request.user.is_staff:
            return Response({"detail": "Landlord only endpoint."}, status=403)
        settings_obj = self._get_settings(request.user)
        return Response(LandlordSettingsSerializer(settings_obj).data)

    def patch(self, request):
        if get_role(request.user) != Profile.ROLE_LANDLORD and not request.user.is_staff:
            return Response({"detail": "Landlord only endpoint."}, status=403)
        settings_obj = self._get_settings(request.user)
        serializer = LandlordSettingsSerializer(
            settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class STKInitiateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [STKInitiateRateThrottle]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Unauthorized request."}, status=403)

        missing_env_vars = _missing_intasend_env_vars()
        if missing_env_vars:
            logger.warning(
                "M-Pesa initiate blocked: missing IntaSend env vars %s",
                missing_env_vars,
            )
            return Response(
                {
                    "detail": "Payment gateway is not configured.",
                    "missing_env_vars": missing_env_vars,
                },
                status=503,
            )

        serializer = STKInitiateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lease = serializer.validated_data["lease"]
        try:
            _assert_active_lease(lease, request.user)
        except PermissionDenied:
            return Response({"detail": "Unauthorized request."}, status=403)
        except DRFValidationError:
            return Response({"detail": "No active lease found."}, status=400)

        period = _current_period()
        billing_period = current_billing_period()
        requested_amount = serializer.validated_data["amount"]
        wallet_applied = Decimal("0.00")
        wallet_payment = None
        payment = None

        with transaction.atomic():
            lease = (
                Lease.objects.select_for_update()
                .select_related("tenant", "unit", "unit__property")
                .get(pk=lease.pk)
            )
            _validate_payment_amount(lease, requested_amount, billing_period)

            tenant_profile, _ = Profile.objects.get_or_create(
                user=request.user)
            Profile.objects.select_for_update().get(pk=tenant_profile.pk)

            landlord_balance, _ = LandlordBalance.objects.get_or_create(
                landlord=lease.unit.property.landlord
            )
            LandlordBalance.objects.select_for_update().get(pk=landlord_balance.pk)

            # Wallet credits are balance-based, so they reduce rent immediately
            # before we decide whether an STK push is still needed.
            wallet_applied = _apply_wallet_to_current_rent(lease)
            remaining_balance = max(
                compute_lease_rent_status(
                    lease,
                    period=period,
                    today=timezone.localdate(),
                ).get("balance", Decimal("0.00")),
                Decimal("0.00"),
            )

            if remaining_balance <= 0:
                wallet_payment = (
                    PaymentTransaction.objects.filter(
                        lease=lease,
                        tenant=request.user,
                        amount=wallet_applied,
                        status=PaymentTransaction.STATUS_SUCCESS,
                        allocation_done=True,
                        result_desc="Auto wallet rent debit",
                    )
                    .order_by("-created_at")
                    .first()
                )
            else:
                payment = PaymentTransaction.objects.create(
                    lease=lease,
                    tenant=request.user,
                    period=period,
                    billing_period=billing_period,
                    phone_number=serializer.validated_data["phone_number"],
                    amount=min(requested_amount, remaining_balance),
                    payment_method=PaymentTransaction.METHOD_MPESA,
                    status=PaymentTransaction.STATUS_PENDING,
                )

        if wallet_payment is not None:
            return Response(
                {
                    "detail": "Rent was fully covered by wallet credit.",
                    "payment": PaymentTransactionSerializer(wallet_payment).data,
                    "wallet_applied": wallet_applied,
                },
                status=200,
            )

        result = intasend_stk_push(
            payment.phone_number, payment.amount, f"LEASE-{lease.id}")
        if not result.get("success"):
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.result_desc = result.get(
                "error") or "Payment failed. Please try again."
            payment.save(update_fields=["status", "result_desc"])
            return Response({"detail": payment.result_desc}, status=502)

        invoice_id = str(result.get("invoice_id") or "").strip()
        if not invoice_id:
            payment.status = PaymentTransaction.STATUS_FAILED
            payment.result_desc = "IntaSend did not return an invoice id."
            payment.save(update_fields=["status", "result_desc"])
            return Response({"detail": payment.result_desc}, status=502)

        payment.merchant_request_id = invoice_id
        payment.checkout_request_id = invoice_id
        payment.result_desc = "STK push initiated."
        payment.save(update_fields=[
                     "merchant_request_id", "checkout_request_id", "result_desc"])

        return Response({"detail": "STK push initiated.", "payment": PaymentTransactionSerializer(payment).data}, status=201)


class STKCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw_body = request.body or b""
        signature = request.META.get("HTTP_X_INTASEND_SIGNATURE", "")

        # IntaSend signs the exact raw webhook body, so verify that before trusting
        # any parsed fields from the callback payload.
        if not _verify_intasend_signature(raw_body, signature):
            logger.warning("payment.intasend.invalid_signature")
            return Response({"detail": "Invalid signature."}, status=400)

        try:
            payload = request.data if isinstance(request.data, dict) else {}
        except Exception:
            logger.warning("payment.intasend.bad_payload")
            return Response({"detail": "Invalid payload."}, status=400)

        # Normalize into the shared event format and hand off. All security
        # checks (amount, lease, idempotency) live in apply_payment_event so
        # adding Pesapal/Daraja later cannot accidentally skip one.
        try:
            event = normalize_intasend_callback(payload)
        except Exception:
            logger.exception("payment.intasend.normalize_failed")
            return Response({"detail": "Invalid payload."}, status=400)

        result = apply_payment_event(event)

        # Post-allocation side effects: receipt + SMS. We do these in the view
        # so the payment core stays I/O-free and easy to test.
        # Only the first-time SUCCESS transition triggers receipts/SMS. The
        # "allocation_retried" path is a back-fill for a previous event that
        # already sent those notifications, so we must not double them up.
        if result.ok and result.code == "applied" and result.payment_id is not None:
            payment = (
                PaymentTransaction.objects.select_related(
                    "lease", "lease__unit", "lease__unit__property", "tenant"
                )
                .filter(pk=result.payment_id)
                .first()
            )
            if payment:
                try:
                    save_payment_receipt(payment)
                except Exception:
                    logger.exception("payment.intasend.receipt_failed payment_id=%s", payment.id)
                tenant_profile = getattr(payment.tenant, "profile", None)
                phone_number = getattr(tenant_profile, "phone_number", "") or payment.phone_number
                if phone_number:
                    try:
                        send_sms(
                            phone_number,
                            f"KRIB payment received for {payment.period}. Receipt: {payment.transaction_code or payment.id}",
                        )
                    except Exception:
                        logger.exception("payment.intasend.sms_failed payment_id=%s", payment.id)

        return Response({"detail": result.detail or "Callback processed."}, status=200)


class MPesaPaymentStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, checkout_id):
        payment = PaymentTransaction.objects.filter(checkout_request_id=checkout_id).select_related(
            "lease", "lease__unit", "lease__unit__property", "tenant").first()
        if not payment:
            return Response({"detail": "Payment not found."}, status=404)
        if payment.tenant_id != request.user.id:
            return Response({"detail": "Unauthorized request."}, status=403)
        return Response(
            {
                "checkout_id": checkout_id,
                "status": payment.status,
                "payment": PaymentTransactionSerializer(payment).data,
            }
        )


class PayPalCreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Unauthorized request."}, status=403)

        lease_id = request.data.get("lease_id")
        amount = request.data.get("amount")
        lease = Lease.objects.filter(pk=lease_id).select_related(
            "unit", "unit__property", "tenant").first()
        try:
            _assert_active_lease(lease, request.user)
        except PermissionDenied:
            return Response({"detail": "Unauthorized request."}, status=403)
        except DRFValidationError:
            return Response({"detail": "No active lease found."}, status=400)

        billing_period = current_billing_period()
        _validate_payment_amount(lease, amount, billing_period)

        order = paypal_create_order(
            amount, f"lease-{lease.id}-{_current_period()}")
        if not order or order.get("error") or not order.get("id"):
            detail = order.get("detail") if isinstance(
                order, dict) else "Payment failed. Please try again."
            error_status = order.get(
                "status", 502) if isinstance(order, dict) else 502
            return Response({"detail": detail}, status=error_status)

        payment = PaymentTransaction.objects.create(
            lease=lease,
            tenant=request.user,
            period=_current_period(),
            billing_period=billing_period,
            phone_number=getattr(
                getattr(request.user, "profile", None), "phone_number", ""),
            amount=amount,
            payment_method=PaymentTransaction.METHOD_PAYPAL,
            paypal_order_id=order["id"],
            checkout_request_id=order["id"],
            status=PaymentTransaction.STATUS_PENDING,
            raw_callback=order,
        )
        return Response({"order": order, "payment": PaymentTransactionSerializer(payment).data}, status=201)


class PayPalCaptureView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Unauthorized request."}, status=403)

        order_id = request.data.get("order_id")
        payment = (
            PaymentTransaction.objects.filter(paypal_order_id=order_id, tenant=request.user)
            .select_related("lease", "lease__unit", "lease__unit__property", "tenant")
            .first()
        )
        if not payment:
            return Response({"detail": "Payment not found."}, status=404)

        capture = paypal_capture_order(order_id)
        if not capture or capture.get("error"):
            detail = capture.get("detail") if isinstance(capture, dict) and capture.get("detail") else "Payment failed. Please try again."
            # Mark failed via the payment core so we get the same idempotency
            # contract as the other providers.
            apply_payment_event(
                normalize_paypal_capture(
                    {"id": order_id, "status": "FAILED"},
                    expected_lease_id=payment.lease_id,
                    expected_tenant_id=payment.tenant_id,
                )
            )
            return Response(
                {"detail": detail},
                status=capture.get("status", 502) if isinstance(capture, dict) else 502,
            )

        normalized = normalize_paypal_capture(
            capture,
            expected_lease_id=payment.lease_id,
            expected_tenant_id=payment.tenant_id,
        )
        result = apply_payment_event(normalized)

        if not result.ok:
            return Response({"detail": result.detail, "code": result.code}, status=400)

        if result.code == "applied" and result.payment_id is not None:
            fresh = (
                PaymentTransaction.objects.select_related(
                    "lease", "lease__unit", "lease__unit__property", "tenant"
                )
                .filter(pk=result.payment_id)
                .first()
            )
            if fresh:
                try:
                    save_payment_receipt(fresh)
                except Exception:
                    logger.exception("payment.paypal.receipt_failed payment_id=%s", fresh.id)
                profile = getattr(request.user, "profile", None)
                phone_number = getattr(profile, "phone_number", "")
                if phone_number:
                    try:
                        send_sms(
                            phone_number,
                            f"KRIB payment received for {fresh.period}. Receipt: {fresh.transaction_code}",
                        )
                    except Exception:
                        logger.exception("payment.paypal.sms_failed payment_id=%s", fresh.id)
                return Response({"payment": PaymentTransactionSerializer(fresh).data})

        # Duplicate / non-terminal — return current row state.
        payment.refresh_from_db()
        return Response({"payment": PaymentTransactionSerializer(payment).data})


class StripeCreateIntentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_TENANT:
            return Response({"detail": "Unauthorized request."}, status=403)

        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
        if stripe is None or not stripe_secret_key:
            return Response({"detail": "Payment failed. Please try again."}, status=503)

        lease_id = request.data.get("lease_id")
        amount = request.data.get("amount")
        lease = Lease.objects.filter(pk=lease_id).select_related(
            "unit", "unit__property", "tenant").first()
        try:
            _assert_active_lease(lease, request.user)
        except PermissionDenied:
            return Response({"detail": "Unauthorized request."}, status=403)
        except DRFValidationError:
            return Response({"detail": "No active lease found."}, status=400)

        billing_period = current_billing_period()
        _validate_payment_amount(lease, amount, billing_period)

        stripe.api_key = stripe_secret_key
        currency = os.getenv("STRIPE_CURRENCY", "kes").strip().lower() or "kes"
        metadata = {
            "tenant_id": str(request.user.id),
            "lease_id": str(lease.id),
            "billing_period": str(billing_period),
            "period": _current_period(),
        }
        try:
            intent = stripe.PaymentIntent.create(
                amount=int((Decimal(amount) * 100).quantize(Decimal("1"))),
                currency=currency,
                automatic_payment_methods={"enabled": True},
                metadata=metadata,
                description=f"KRIB rent payment for lease {lease.id} - {_current_period()}",
            )
        except stripe.error.StripeError as exc:
            logger.warning("Stripe create intent failed: %s", exc)
            return Response({"detail": "Payment failed. Please try again."}, status=502)

        payment = PaymentTransaction.objects.create(
            lease=lease,
            tenant=request.user,
            period=_current_period(),
            billing_period=billing_period,
            phone_number=getattr(
                getattr(request.user, "profile", None), "phone_number", "") or "CARD",
            amount=amount,
            payment_method=PaymentTransaction.METHOD_CARD,
            stripe_payment_intent_id=intent["id"],
            checkout_request_id=intent["id"],
            status=PaymentTransaction.STATUS_PENDING,
            raw_callback=intent,
        )
        return Response(
            {
                "client_secret": intent["client_secret"],
                "payment_intent_id": intent["id"],
                "publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip(),
                "payment": PaymentTransactionSerializer(payment).data,
            },
            status=201,
        )


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        if stripe is None or not stripe_secret_key:
            return Response({"detail": "Payment failed. Please try again."}, status=503)

        # Fail closed: a missing webhook secret means we cannot authenticate the
        # event, so we must NOT mark any payment successful.
        if not webhook_secret:
            logger.error("payment.stripe.no_secret")
            return Response({"detail": "Webhook secret not configured."}, status=503)

        stripe.api_key = stripe_secret_key
        payload = request.body
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        try:
            event = stripe.Webhook.construct_event(
                payload=payload, sig_header=signature, secret=webhook_secret)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            logger.warning("payment.stripe.invalid_signature %s", redact_text(str(exc)))
            return Response({"detail": "Unauthorized request."}, status=400)

        # Normalize + apply via the shared payment core. Amount/currency/
        # lease/tenant checks live there; this view only does signature
        # verification + side effects.
        try:
            normalized = normalize_stripe_event(event)
        except Exception:
            logger.exception("payment.stripe.normalize_failed")
            return Response({"detail": "Invalid payload."}, status=400)

        result = apply_payment_event(normalized)

        # Only the first-time SUCCESS transition triggers receipts/SMS. The
        # "allocation_retried" path is a back-fill for a previous event that
        # already sent those notifications, so we must not double them up.
        if result.ok and result.code == "applied" and result.payment_id is not None:
            payment = (
                PaymentTransaction.objects.select_related(
                    "lease", "lease__unit", "lease__unit__property", "tenant"
                )
                .filter(pk=result.payment_id)
                .first()
            )
            if payment:
                try:
                    save_payment_receipt(payment)
                except Exception:
                    logger.exception("payment.stripe.receipt_failed payment_id=%s", payment.id)
                tenant_profile = getattr(payment.tenant, "profile", None)
                phone_number = getattr(tenant_profile, "phone_number", "") or payment.phone_number
                if phone_number:
                    try:
                        send_sms(
                            phone_number,
                            f"KRIB payment received for {payment.period}. Receipt: {payment.transaction_code}",
                        )
                    except Exception:
                        logger.exception("payment.stripe.sms_failed payment_id=%s", payment.id)

        return Response({"detail": result.detail or "Webhook processed."}, status=200)


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        qs = PaymentTransaction.objects.select_related(
            "lease", "lease__unit", "lease__unit__property", "tenant")
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payments_arrears(request):
    if _get_role(request.user) != Profile.ROLE_LANDLORD:
        return Response({"detail": "Unauthorized request."}, status=403)

    period = request.query_params.get("period") or _current_period()
    today = timezone.localdate()
    rows = []
    leases = Lease.objects.filter(status=Lease.STATUS_ACTIVE, unit__property__landlord=request.user).select_related(
        "tenant", "unit", "unit__property")
    for lease in leases:
        rent = compute_lease_rent_status(lease, period=period, today=today)
        if rent["status"] != "OVERDUE":
            continue
        rows.append(
            {
                "lease_id": lease.id,
                "tenant_id": lease.tenant_id,
                "tenant_name": _display_name(lease.tenant),
                "property_name": lease.unit.property.name,
                "unit_number": lease.unit.unit_number,
                "billing_period": period,
                "rent_due": rent["rent_due"],
                "amount_paid": rent["paid_sum"],
                "balance": rent["balance"],
                "status": rent["status"],
                "cumulative_paid_sum": rent.get("cumulative_paid_sum", rent.get("paid_sum", Decimal("0.00"))),
            }
        )
    return Response(rows)


class PaymentReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        payment = PaymentTransaction.objects.filter(pk=pk).select_related(
            "lease", "lease__unit", "lease__unit__property", "tenant").first()
        if not payment:
            raise Http404("Payment not found.")
        if not _user_can_access_payment_receipt(request.user, payment):
            return Response({"detail": "Unauthorized request."}, status=403)
        if payment.status != PaymentTransaction.STATUS_SUCCESS:
            return Response({"detail": "Payment failed. Please try again."}, status=400)
        if not payment.receipt_file:
            save_payment_receipt(payment)
        if not payment.receipt_file:
            return Response({"detail": "Receipt generation is currently unavailable."}, status=503)
        return FileResponse(
            payment.receipt_file.open("rb"),
            as_attachment=True,
            content_type="application/pdf",
            filename=os.path.basename(payment.receipt_file.name),
        )


class DocumentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = _get_role(request.user)
        if role == Profile.ROLE_LANDLORD:
            docs = Document.objects.filter(property__landlord=request.user).select_related(
                "property", "lease", "lease__unit", "uploaded_by", "tenant")
        elif role == Profile.ROLE_MANAGER:
            docs = Document.objects.filter(property__manager=request.user).select_related(
                "property", "lease", "lease__unit", "uploaded_by", "tenant")
        elif role == Profile.ROLE_TENANT:
            # Tenants ONLY see documents that explicitly target them. The old
            # query also returned any TYPE_LEASE/TYPE_OTHER document attached
            # to any unit in any property they rent, which leaked other
            # tenants' lease agreements and IDs to a co-tenant in the same
            # building.
            tenant_leases = Lease.objects.filter(tenant=request.user)
            docs = Document.objects.filter(
                Q(tenant=request.user) | Q(lease__in=tenant_leases)
            ).distinct().select_related(
                "property", "lease", "lease__unit", "uploaded_by", "tenant"
            )
        else:
            return Response([], status=200)
        return Response(DocumentSerializer(docs, many=True, context={"request": request}).data)


class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        property_id = request.data.get("property")
        property_obj = Property.objects.filter(pk=property_id).first()
        if not property_obj:
            return Response({"detail": "Property not found."}, status=404)

        # Allow-list style check: a request must positively match one of the
        # legitimate scopes. The previous chain only enumerated rejection
        # branches, so a landlord uploading to their own property fell through
        # every `elif` to the trailing `else: 403`.
        role = _get_role(request.user)
        allowed = False
        if request.user.is_staff:
            allowed = True
        elif role == Profile.ROLE_LANDLORD and property_obj.landlord_id == request.user.id:
            allowed = True
        elif role == Profile.ROLE_MANAGER and property_obj.manager_id == request.user.id:
            allowed = True
        elif role == Profile.ROLE_TENANT and Lease.objects.filter(
            tenant=request.user,
            unit__property=property_obj,
            status=Lease.STATUS_ACTIVE,
        ).exists():
            allowed = True
        if not allowed:
            return Response({"detail": "Unauthorized request."}, status=403)

        # Pass request context so the scoped PrimaryKeyRelatedFields on
        # DocumentSerializer can resolve their queryset against the requester.
        serializer = DocumentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        lease = serializer.validated_data.get("lease")
        document_type = serializer.validated_data.get("document_type")
        tenant = serializer.validated_data.get("tenant")
        if role in [Profile.ROLE_LANDLORD, Profile.ROLE_MANAGER] and document_type in [Document.TYPE_LEASE, Document.TYPE_IDENTITY]:
            return Response(
                {"detail": "Lease agreements and ID / passport files are created during lease onboarding."},
                status=400,
            )
        if document_type == Document.TYPE_IDENTITY and not tenant:
            tenant = getattr(lease, "tenant", None)
            if not tenant:
                return Response({"detail": "Select a lease tied to the tenant ID or passport."}, status=400)
        document = serializer.save(uploaded_by=request.user, tenant=tenant)
        return Response(DocumentSerializer(document, context={"request": request}).data, status=201)


class DocumentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        document = Document.objects.filter(pk=pk).select_related(
            "property", "lease", "uploaded_by").first()
        if not document:
            raise Http404("Document not found.")
        if not _user_can_access_document(request.user, document):
            return Response({"detail": "Unauthorized request."}, status=403)
        # Force attachment download so uploaded user content (HTML/SVG renamed to
        # PDF) cannot be rendered inline in a victim's browser.
        return FileResponse(
            document.file_path.open("rb"),
            as_attachment=True,
            filename=os.path.basename(document.file_path.name),
            content_type="application/octet-stream",
        )


class MediaProxyView(APIView):
    """Permission-checked replacement for the legacy public nginx /media/ alias.

    Every uploaded file lives under MEDIA_ROOT and is reachable as
    /media/<subdir>/<filename>. This view looks up the matching DB row
    (Document, PaymentTransaction.receipt_file, MaintenanceRequest.photo_path)
    and re-runs the same access checks the dedicated endpoints use, then
    serves the bytes as an attachment.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, relative_path):
        # Defence in depth against path traversal even though Django's URL
        # routing already strips ".." segments.
        if ".." in relative_path or relative_path.startswith("/"):
            raise Http404("File not found.")

        normalized = relative_path.lstrip("/")
        document = Document.objects.filter(file_path=normalized).select_related(
            "property", "lease", "uploaded_by").first()
        if document:
            if not _user_can_access_document(request.user, document):
                return Response({"detail": "Unauthorized request."}, status=403)
            return FileResponse(
                document.file_path.open("rb"),
                as_attachment=True,
                filename=os.path.basename(document.file_path.name),
                content_type="application/octet-stream",
            )

        payment = PaymentTransaction.objects.filter(receipt_file=normalized).select_related(
            "lease", "lease__unit", "lease__unit__property", "tenant").first()
        if payment:
            if not _user_can_access_payment_receipt(request.user, payment):
                return Response({"detail": "Unauthorized request."}, status=403)
            return FileResponse(
                payment.receipt_file.open("rb"),
                as_attachment=True,
                filename=os.path.basename(payment.receipt_file.name),
                content_type="application/pdf",
            )

        maintenance = MaintenanceRequest.objects.filter(photo_path=normalized).select_related(
            "tenant", "lease", "lease__unit", "lease__unit__property").first()
        if maintenance:
            role = _get_role(request.user)
            allowed = (
                request.user.id == maintenance.tenant_id
                or (role == Profile.ROLE_LANDLORD and maintenance.lease.unit.property.landlord_id == request.user.id)
                or (role == Profile.ROLE_MANAGER and maintenance.lease.unit.property.manager_id == request.user.id)
                or request.user.is_staff
            )
            if not allowed:
                return Response({"detail": "Unauthorized request."}, status=403)
            return FileResponse(
                maintenance.photo_path.open("rb"),
                as_attachment=True,
                filename=os.path.basename(maintenance.photo_path.name),
                content_type="application/octet-stream",
            )

        raise Http404("File not found.")


class MaintenanceViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        qs = MaintenanceRequest.objects.select_related(
            "tenant", "lease", "lease__unit", "lease__unit__property")
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
            raise PermissionDenied(
                "Only tenants can create maintenance requests")
        lease = serializer.validated_data["lease"]
        if lease.tenant != self.request.user:
            raise PermissionDenied("Can only report for your lease")
        request_row = serializer.save(tenant=self.request.user)
        _notify_users(
            [lease.unit.property.landlord, lease.unit.property.manager],
            "New maintenance request",
            f"{_display_name(lease.tenant)} reported a {request_row.urgency} priority issue for {lease.unit.property.name} / {lease.unit.unit_number}.",
            lease=lease,
        )

    def perform_update(self, serializer):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_TENANT:
            raise PermissionDenied(
                "Tenants cannot update maintenance requests.")
        changed_fields = set(self.request.data.keys())
        if changed_fields - {"status"}:
            raise PermissionDenied(
                "Only maintenance status updates are allowed.")

        previous_status = self.get_object().status
        updated = serializer.save()
        if previous_status != updated.status:
            _notify_users(
                [updated.tenant],
                "Maintenance status updated",
                f"Your maintenance request for {updated.lease.unit.property.name} / {updated.lease.unit.unit_number} is now {updated.get_status_display()}.",
                lease=updated.lease,
            )


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        role = _get_role(self.request.user)
        if role == Profile.ROLE_LANDLORD:
            scoped_properties = Property.objects.filter(
                landlord=self.request.user)
        elif role == Profile.ROLE_MANAGER:
            scoped_properties = Property.objects.filter(
                manager=self.request.user)
        else:
            return Tenant.objects.filter(user=self.request.user)

        accepted_invites = TenantInvite.objects.filter(
            property__in=scoped_properties,
            status=TenantInvite.STATUS_ACCEPTED,
        )
        invite_emails = [email for email in accepted_invites.values_list(
            "email", flat=True) if email]
        invite_phones = [phone for phone in accepted_invites.values_list(
            "phone", flat=True) if phone]

        filters = Q(user__leases__unit__property__in=scoped_properties)
        if invite_emails:
            filters |= Q(user__email__in=invite_emails)
        if invite_phones:
            filters |= Q(phone__in=invite_phones) | Q(
                user__profile__phone_number__in=invite_phones)

        return Tenant.objects.filter(filters).select_related("user").distinct().order_by("user__username")


class NotificationViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_update(self, serializer):
        changed_fields = set(self.request.data.keys())
        if changed_fields - {"is_read"}:
            raise PermissionDenied("Only read state updates are allowed.")
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"detail": "Notifications marked as read."})

    @action(detail=False, methods=["delete"], url_path="clear-read", url_name="clear-read")
    def clear_read(self, request):
        deleted_count, _ = self.get_queryset().filter(is_read=True).delete()
        return Response({"detail": "Read notifications cleared.", "count": deleted_count})

    @action(detail=False, methods=["post"], url_path="send", url_name="send")
    def send_notification(self, request):
        serializer = NotificationSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        recipients = list(
            _notification_recipients(
                request.user,
                serializer.validated_data["audience"],
                serializer.validated_data.get("property"),
            )
        )
        if not recipients:
            return Response({"detail": "No recipients matched the selected audience."}, status=status.HTTP_400_BAD_REQUEST)

        title = serializer.validated_data["title"].strip()
        message = serializer.validated_data["message"].strip()
        send_in_app = serializer.validated_data.get("send_in_app", True)
        send_email = serializer.validated_data.get("send_email", False)
        send_sms_selected = serializer.validated_data.get("send_sms", False)

        count = len(recipients)
        suffix = "" if count == 1 else "s"
        delivered = {"in_app": 0, "email": 0, "sms": 0}
        warnings = []

        if send_in_app:
            Notification.objects.bulk_create(
                [
                    Notification(
                        user=recipient,
                        title=title,
                        message=message,
                        type=Notification.TYPE_GENERIC,
                    )
                    for recipient in recipients
                ]
            )
            delivered["in_app"] = count

        if send_email:
            if not _can_send_email():
                warnings.append(
                    "Email skipped because SMTP is not configured.")
            else:
                missing_email = 0
                for recipient in recipients:
                    if not recipient.email:
                        missing_email += 1
                        continue
                    try:
                        send_mail(
                            subject=title,
                            message=message,
                            from_email=getattr(
                                settings, "DEFAULT_FROM_EMAIL", None),
                            recipient_list=[recipient.email],
                            fail_silently=False,
                        )
                        delivered["email"] += 1
                    except Exception as exc:  # pragma: no cover - env dependent
                        logger.warning(
                            "Notification email delivery failed: %s", exc)
                if missing_email:
                    warnings.append(
                        f"Email skipped for {missing_email} recipient{'' if missing_email == 1 else 's'} without an email address.")

        if send_sms_selected:
            missing_phone = 0
            sms_failures = []
            for recipient in recipients:
                phone_number = _user_phone_number(recipient)
                if not phone_number:
                    missing_phone += 1
                    continue
                sms_result = send_sms(
                    phone_number, message, include_detail=True)
                sms_ok = sms_result if isinstance(
                    sms_result, bool) else sms_result.get("ok")
                sms_detail = "" if isinstance(
                    sms_result, bool) else sms_result.get("detail")
                if sms_ok:
                    delivered["sms"] += 1
                else:
                    sms_failures.append(sms_detail or "SMS delivery failed.")
            if missing_phone:
                warnings.append(
                    f"SMS skipped for {missing_phone} recipient{'' if missing_phone == 1 else 's'} without a phone number.")
            if sms_failures:
                warnings.append(
                    f"SMS failed for {len(sms_failures)} recipient{'' if len(sms_failures) == 1 else 's'}: {sms_failures[0]}")

        any_delivery = delivered["in_app"] or delivered["email"] or delivered["sms"]
        if not any_delivery:
            detail = warnings[0] if warnings else "No notification could be delivered."
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE if send_email or send_sms_selected else status.HTTP_400_BAD_REQUEST
            return Response({"detail": detail, "count": count, "delivery": delivered}, status=status_code)

        detail_parts = [f"Notification sent to {count} recipient{suffix}."]
        if send_in_app:
            detail_parts.append(f"In-app: {delivered['in_app']}.")
        if send_email:
            detail_parts.append(f"Email: {delivered['email']}.")
        if send_sms_selected:
            detail_parts.append(f"SMS: {delivered['sms']}.")
        if warnings:
            detail_parts.append(" ".join(warnings))

        return Response(
            {"detail": " ".join(detail_parts), "count": count,
             "delivery": delivered},
            status=status.HTTP_201_CREATED,
        )


@api_view(["PATCH", "POST"])
@permission_classes([IsAuthenticated])
def notifications_read_all(request):
    Notification.objects.filter(
        user=request.user, is_read=False).update(is_read=True)
    return Response({"detail": "Notifications marked as read."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tenant_dashboard(request):
    if _get_role(request.user) != Profile.ROLE_TENANT:
        return Response({"detail": "Unauthorized request."}, status=403)

    lease = _tenant_active_lease(request.user)
    if not lease:
        return Response(
            {
                "rent_status": "NO_ACTIVE_LEASE",
                "amount_due": Decimal("0.00"),
                "current_period": _current_period(),
                "recent_payments": [],
                "open_maintenance_requests": [],
                "unread_notification_count": Notification.objects.filter(user=request.user, is_read=False).count(),
            }
        )

    period = _current_period()
    rent = compute_lease_rent_status(lease, period=period)
    recent_payments = PaymentTransaction.objects.filter(
        tenant=request.user).order_by("-created_at")[:5]
    open_maintenance = MaintenanceRequest.objects.filter(tenant=request.user).exclude(
        status=MaintenanceRequest.STATUS_RESOLVED).order_by("-updated_at")
    return Response(
        {
            "rent_status": rent["status"],
            "amount_due": rent["balance"],
            "current_period": period,
            "recent_payments": PaymentTransactionSerializer(recent_payments, many=True).data,
            "open_maintenance_requests": MaintenanceRequestSerializer(open_maintenance, many=True).data,
            "unread_notification_count": Notification.objects.filter(user=request.user, is_read=False).count(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def landlord_dashboard(request):
    if _get_role(request.user) != Profile.ROLE_LANDLORD:
        return Response({"detail": "Unauthorized request."}, status=403)

    period = _current_period()
    today = timezone.localdate()
    properties = Property.objects.filter(landlord=request.user)
    units = Unit.objects.filter(property__landlord=request.user)
    leases = Lease.objects.filter(status=Lease.STATUS_ACTIVE, unit__property__landlord=request.user).select_related(
        "tenant", "unit", "unit__property")
    payments = PaymentTransaction.objects.filter(
        lease__unit__property__landlord=request.user,
        status=PaymentTransaction.STATUS_SUCCESS,
        billing_period=period_string_to_date(period),
    )

    tenants_in_arrears = []
    total_arrears = Decimal("0.00")
    for lease in leases:
        rent = compute_lease_rent_status(lease, period=period, today=today)
        if rent["status"] == "OVERDUE":
            total_arrears += max(rent["balance"], Decimal("0.00"))
            tenants_in_arrears.append(
                {
                    "lease_id": lease.id,
                    "tenant_name": _display_name(lease.tenant),
                    "property_name": lease.unit.property.name,
                    "unit_number": lease.unit.unit_number,
                    "balance": rent["balance"],
                }
            )

    pending_maintenance = MaintenanceRequest.objects.filter(
        lease__unit__property__landlord=request.user,
    ).exclude(status=MaintenanceRequest.STATUS_RESOLVED)
    recent_payments = PaymentTransaction.objects.filter(
        lease__unit__property__landlord=request.user,
    ).order_by("-created_at")[:5]

    return Response(
        {
            "total_properties": properties.count(),
            "occupied_units": units.filter(status=Unit.STATUS_OCCUPIED).count(),
            "vacant_units": units.filter(status=Unit.STATUS_VACANT).count(),
            "total_collected_this_month": payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
            "total_arrears": total_arrears,
            "tenants_in_arrears": tenants_in_arrears,
            "pending_maintenance": pending_maintenance.count(),
            "recent_payments": PaymentTransactionSerializer(recent_payments, many=True).data,
            "unread_notification_count": Notification.objects.filter(user=request.user, is_read=False).count(),
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    role = _get_role(request.user)
    period = request.query_params.get(
        "period") or timezone.localdate().strftime("%Y-%m")

    if role == Profile.ROLE_TENANT:
        lease = (
            Lease.objects.filter(tenant=request.user,
                                 status=Lease.STATUS_ACTIVE)
            .select_related("unit", "unit__property")
            .first()
        )
        if not lease:
            return Response({"active_lease": None, "rent": {}, "payments": [], "maintenance": [], "show_overdue_banner": False})
        rent = compute_lease_rent_status(lease, period=period)
        profile = Profile.objects.filter(
            user=request.user).only("wallet_available").first()
        rent = _wallet_aware_rent_status(
            lease,
            rent,
            getattr(profile, "wallet_available", Decimal("0.00")),
        )
        payments = PaymentTransaction.objects.filter(
            tenant=request.user).order_by("-created_at")[:10]
        maintenance = MaintenanceRequest.objects.filter(
            tenant=request.user).order_by("-updated_at")[:10]
        active_lease = LeaseSerializer(lease, context={"period": period}).data
        active_lease["rent_status"] = rent
        return Response(
            {
                "period": period,
                "active_lease": active_lease,
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
                "tenant": _display_name(lease.tenant),
                "tenant_email": lease.tenant.email,
                "tenant_phone_number": getattr(getattr(lease.tenant, "profile", None), "phone_number", "") or getattr(getattr(lease.tenant, "tenant_profile", None), "phone", ""),
                "unit": f"{lease.unit.property.name} / {lease.unit.unit_number}",
                "rent_due": status_row["rent_due"],
                "paid_sum": status_row["paid_sum"],
                "balance": status_row["balance"],
                "status": status_row["status"],
                "cumulative_paid_sum": status_row.get("cumulative_paid_sum", status_row.get("paid_sum", Decimal("0.00"))),
                "carried_forward_balance": status_row.get("carried_forward_balance", Decimal("0.00")),
            }
        )

    maintenance_qs = MaintenanceRequest.objects.select_related(
        "tenant", "lease", "lease__unit", "lease__unit__property")
    if role == Profile.ROLE_MANAGER:
        maintenance_qs = maintenance_qs.filter(
            lease__unit__property__manager=request.user)
    elif role == Profile.ROLE_LANDLORD:
        maintenance_qs = maintenance_qs.filter(
            lease__unit__property__landlord=request.user)

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
        recent = LedgerTransaction.objects.filter(
            user=request.user, kind__startswith="WALLET").order_by("-created_at")[:20]
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

        allowed, message = can_withdraw_wallet(request.user, amount)
        if not allowed:
            return Response({"detail": message}, status=400)

        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=request.user)
            profile = Profile.objects.select_for_update().get(pk=profile.pk)
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
        balance, _ = LandlordBalance.objects.get_or_create(
            landlord=request.user)
        _unlock_landlord(balance)
        payouts = LandlordPayout.objects.filter(
            landlord=request.user).order_by("-created_at")
        return Response(
            {
                "available_balance": balance.available_balance,
                "locked_balance": balance.locked_balance,
                "payout_requests": LandlordPayoutSerializer(payouts, many=True).data,
            }
        )


def _normalized_destination(method, destination):
    """Canonicalize a payout destination so saved-vs-submitted comparisons are stable."""
    text = (destination or "").strip()
    if method == LandlordPayout.METHOD_MPESA:
        return normalize_mpesa_phone_number(text) or text
    return re.sub(r"\s+", "", text)


def _matches_saved_destination(user, method, destination, bank_code):
    """Return True iff the submitted destination matches the landlord's saved
    payout method. This is the load-bearing guard that prevents a hijacked
    landlord session from instantly draining the balance to an attacker-chosen
    account."""
    try:
        saved = user.landlord_settings
    except LandlordSettings.DoesNotExist:
        return False

    saved_method = (saved.payout_method or "").upper()
    if saved_method != str(method or "").upper():
        return False

    submitted = _normalized_destination(method, destination)
    saved_dest = _normalized_destination(method, saved.payout_destination or "")
    if not submitted or submitted != saved_dest:
        return False

    if method == LandlordPayout.METHOD_BANK:
        saved_bank = (saved.payout_bank_code or "").strip()
        submitted_bank = (bank_code or "").strip()
        if saved_bank != submitted_bank:
            return False

    return True


def _release_payout_reservation(landlord, amount):
    """Atomically refund `amount` to landlord.available_balance.

    Used by FAILED and REVERSED transitions. We re-lock the balance row so
    a concurrent payout request cannot race with the refund.
    """
    with transaction.atomic():
        balance, _ = LandlordBalance.objects.get_or_create(landlord=landlord)
        balance = LandlordBalance.objects.select_for_update().get(pk=balance.pk)
        balance.available_balance = balance.available_balance + amount
        balance.save(update_fields=["available_balance", "updated_at"])


def _record_payout_ledger(*, payout, kind, status, reference_text):
    LedgerTransaction.objects.create(
        user=payout.landlord,
        kind=kind,
        amount=payout.amount,
        status=status,
        reference_text=reference_text,
    )


class LandlordPayoutRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if _get_role(request.user) != Profile.ROLE_LANDLORD:
            return Response({"detail": "Landlord only endpoint"}, status=403)
        serializer = LandlordPayoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]
        method = serializer.validated_data["method"]
        destination = serializer.validated_data["destination"]
        bank_code = serializer.validated_data.get("bank_code")

        if amount <= 0:
            return Response({"detail": "Amount must be greater than zero"}, status=400)

        # Destination + cool-down guards (unchanged from previous pass).
        if not _matches_saved_destination(request.user, method, destination, bank_code):
            return Response(
                {
                    "detail": "Payout destination must match the saved landlord settings.",
                    "code": "destination_not_verified",
                },
                status=403,
            )

        cooldown_hours = max(int(getattr(settings, "LANDLORD_PAYOUT_COOLDOWN_HOURS", 24)), 0)
        try:
            saved = request.user.landlord_settings
            last_change = getattr(saved, "payout_destination_updated_at", None)
        except LandlordSettings.DoesNotExist:
            last_change = None
        if cooldown_hours and last_change:
            elapsed = timezone.now() - last_change
            if elapsed < timedelta(hours=cooldown_hours):
                remaining = timedelta(hours=cooldown_hours) - elapsed
                remaining_minutes = int(remaining.total_seconds() // 60) + 1
                return Response(
                    {
                        "detail": (
                            "Payout destination was changed recently. "
                            f"Please try again in about {remaining_minutes} minutes."
                        ),
                        "code": "destination_cooldown_active",
                    },
                    status=403,
                )

        # ------------------------------------------------------------------
        # Idempotency. Clients can supply an X-Idempotency-Key header or an
        # `idempotency_key` body field; if a payout already exists for this
        # landlord with the same key we return its current state without
        # double-deducting and without re-submitting to the provider.
        # ------------------------------------------------------------------
        raw_key = (
            request.META.get("HTTP_X_IDEMPOTENCY_KEY")
            or (request.data.get("idempotency_key") if isinstance(request.data, dict) else None)
            or ""
        )
        try:
            idempotency_key = uuid.UUID(str(raw_key)) if raw_key else uuid.uuid4()
        except (ValueError, TypeError):
            return Response({"detail": "idempotency_key must be a UUID."}, status=400)

        existing = LandlordPayout.objects.filter(
            landlord=request.user, idempotency_key=idempotency_key
        ).first()
        if existing:
            return Response(LandlordPayoutSerializer(existing).data, status=200)

        # ------------------------------------------------------------------
        # Step 1: reserve funds and persist a REQUESTED row in its own
        # short-lived transaction. We commit BEFORE calling the external
        # provider so a network timeout or crash mid-call leaves us with a
        # row we can reconcile later, not an orphaned deduction.
        # ------------------------------------------------------------------
        normalized_destination = _normalized_destination(method, destination)
        try:
            with transaction.atomic():
                balance, _ = LandlordBalance.objects.get_or_create(landlord=request.user)
                balance = LandlordBalance.objects.select_for_update().get(pk=balance.pk)
                unlock_due_landlord_balance(request.user)
                balance.refresh_from_db()
                if amount > balance.available_balance:
                    return Response({"detail": "Insufficient available balance"}, status=400)
                balance.available_balance = balance.available_balance - amount
                balance.save(update_fields=["available_balance", "updated_at"])
                payout = LandlordPayout.objects.create(
                    landlord=request.user,
                    amount=amount,
                    method=method,
                    destination=normalized_destination,
                    bank_code=bank_code,
                    status=LandlordPayout.STATUS_REQUESTED,
                    requested_by=request.user,
                    idempotency_key=idempotency_key,
                )
                _record_payout_ledger(
                    payout=payout,
                    kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
                    status=LedgerTransaction.STATUS_PENDING,
                    reference_text=f"payout:{payout.id};key:{idempotency_key}",
                )
        except Exception:
            logger.exception("payout.reserve_failed landlord_id=%s", request.user.id)
            return Response({"detail": "Could not reserve funds for this payout."}, status=500)

        logger.info(
            "payout.requested payout_id=%s landlord_id=%s amount=%s method=%s",
            payout.id, request.user.id, str(amount), method,
        )

        # ------------------------------------------------------------------
        # Step 2: call the provider OUTSIDE any open DB transaction.
        # ------------------------------------------------------------------
        result = execute_intasend_payout(payout)
        return self._apply_payout_outcome(payout, result)

    def _apply_payout_outcome(self, payout, result):
        outcome = result.get("outcome")
        provider_reference = result.get("provider_reference")
        provider_status = result.get("provider_status")
        redacted = result.get("redacted_response") or {}
        detail = result.get("detail")

        now = timezone.now()

        if outcome == "rejected":
            # Provider explicitly refused. No money left their system, so we
            # release the reservation and FAIL. We UPDATE the existing
            # PAYOUT_REQUEST ledger row in place (rather than appending a
            # second one) so the audit history stays one-row-per-payout.
            with transaction.atomic():
                locked = LandlordPayout.objects.select_for_update().get(pk=payout.id)
                if locked.status == LandlordPayout.STATUS_REQUESTED:
                    locked.status = LandlordPayout.STATUS_FAILED
                    locked.failed_at = now
                    locked.provider_reference = provider_reference
                    locked.provider_status = provider_status
                    locked.provider_response = redacted
                    locked.save(update_fields=[
                        "status", "failed_at", "provider_reference",
                        "provider_status", "provider_response",
                    ])
            _release_payout_reservation(payout.landlord, payout.amount)
            short_detail = (detail or "")[:120]
            LedgerTransaction.objects.filter(
                user=payout.landlord,
                kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
                reference_text__startswith=f"payout:{payout.id}",
            ).update(
                status=LedgerTransaction.STATUS_REJECTED,
                reference_text=f"payout:{payout.id};provider_reject:{short_detail}",
            )
            return Response({"detail": detail or "Payout was rejected by the provider."}, status=502)

        if outcome == "settled":
            # Provider gave us an unambiguous "settled" answer (rare for
            # async M-Pesa, common on instant rails). Promote straight to PAID.
            return self._mark_paid(payout, provider_reference, provider_status, redacted, source="provider")

        if outcome == "accepted":
            # Provider acknowledged with a tracking id. Payout is PROCESSING.
            # Funds remain reserved. The reconciliation loop / mark-paid
            # admin endpoint will finalize once settlement is confirmed.
            with transaction.atomic():
                locked = LandlordPayout.objects.select_for_update().get(pk=payout.id)
                if locked.status == LandlordPayout.STATUS_REQUESTED:
                    locked.status = LandlordPayout.STATUS_PROCESSING
                    locked.processing_at = now
                    locked.provider_reference = provider_reference
                    locked.provider_status = provider_status
                    locked.provider_response = redacted
                    locked.save(update_fields=[
                        "status", "processing_at", "provider_reference",
                        "provider_status", "provider_response",
                    ])
                payout = locked
            return Response(LandlordPayoutSerializer(payout).data, status=202)

        # ambiguous OR transport_error: the safest default is to KEEP the
        # reservation. If we got a provider_reference we know the request
        # reached IntaSend, so we move to PROCESSING. Otherwise we stay
        # REQUESTED so reconciliation can retry by idempotency key.
        with transaction.atomic():
            locked = LandlordPayout.objects.select_for_update().get(pk=payout.id)
            if provider_reference and locked.status == LandlordPayout.STATUS_REQUESTED:
                locked.status = LandlordPayout.STATUS_PROCESSING
                locked.processing_at = now
            locked.provider_reference = provider_reference or locked.provider_reference
            locked.provider_status = provider_status
            locked.provider_response = redacted
            locked.save(update_fields=[
                "status", "processing_at", "provider_reference",
                "provider_status", "provider_response",
            ])
            payout = locked
        logger.warning(
            "payout.ambiguous payout_id=%s outcome=%s has_ref=%s",
            payout.id, outcome, bool(provider_reference),
        )
        return Response(
            {
                "detail": detail or "Payout was submitted but the provider has not confirmed settlement yet.",
                "code": "payout_processing",
                "payout": LandlordPayoutSerializer(payout).data,
            },
            status=202,
        )

    def _mark_paid(self, payout, provider_reference, provider_status, redacted, *, source):
        with transaction.atomic():
            locked = LandlordPayout.objects.select_for_update().get(pk=payout.id)
            if locked.status == LandlordPayout.STATUS_PAID:
                return Response(LandlordPayoutSerializer(locked).data, status=200)
            if locked.status not in (
                LandlordPayout.STATUS_REQUESTED,
                LandlordPayout.STATUS_PROCESSING,
            ):
                return Response(
                    {"detail": "Payout is no longer in a markable state.", "code": "invalid_state"},
                    status=409,
                )
            now = timezone.now()
            locked.status = LandlordPayout.STATUS_PAID
            locked.paid_at = now
            if not locked.processing_at:
                locked.processing_at = now
            if provider_reference and not locked.provider_reference:
                locked.provider_reference = provider_reference
            if provider_status:
                locked.provider_status = provider_status
            if redacted:
                locked.provider_response = redacted
            locked.save(update_fields=[
                "status", "paid_at", "processing_at",
                "provider_reference", "provider_status", "provider_response",
            ])
            payout = locked
        _record_payout_ledger(
            payout=payout,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
            status=LedgerTransaction.STATUS_PAID,
            reference_text=f"payout:{payout.id};source:{source}",
        )
        # Mark the original REQUEST ledger row as PAID so the audit trail
        # tells the full story.
        LedgerTransaction.objects.filter(
            user=payout.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
            reference_text__startswith=f"payout:{payout.id}",
        ).update(status=LedgerTransaction.STATUS_PAID)
        return Response(LandlordPayoutSerializer(payout).data, status=201)


class LandlordPayoutMarkPaidView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Admin only endpoint"}, status=403)
        payout = LandlordPayout.objects.select_for_update().filter(pk=pk).first()
        if not payout:
            return Response({"detail": "Payout not found"}, status=404)
        if payout.status == LandlordPayout.STATUS_PAID:
            return Response({"detail": "Payout already marked paid."}, status=400)
        # Admin can ONLY finalize payouts that reached PROCESSING. PROCESSING
        # means we successfully submitted to the provider AND received back a
        # provider_reference, so the admin's "yes, it actually settled" is a
        # decision about a real provider-side transaction — not a fabrication.
        #
        # Earlier revisions also accepted the legacy STATUS_PENDING value
        # here. That widened the door enough for staff to "settle" a payout
        # row that had never been sent to IntaSend at all, which is exactly
        # the abuse path this endpoint must close. Legacy PENDING rows must
        # now go through the reverse endpoint (admin confirms no money moved)
        # or be migrated via the reconciler.
        if payout.status != LandlordPayout.STATUS_PROCESSING:
            return Response(
                {
                    "detail": "Only PROCESSING payouts can be marked paid by an admin.",
                    "code": "invalid_state",
                    "current_status": payout.status,
                },
                status=400,
            )
        # And the row MUST already carry a provider_reference. Without one
        # there is no way for the admin to have verified settlement
        # off-platform — they'd be guessing.
        if not (payout.provider_reference or "").strip():
            return Response(
                {
                    "detail": "Payout has no provider reference yet; verify settlement before marking paid.",
                    "code": "missing_provider_reference",
                },
                status=400,
            )
        now = timezone.now()
        payout.status = LandlordPayout.STATUS_PAID
        payout.paid_at = now
        payout.marked_paid_by = request.user
        payout.marked_paid_at = now
        if not payout.processing_at:
            payout.processing_at = now
        payout.save(update_fields=[
            "status", "paid_at", "marked_paid_by", "marked_paid_at", "processing_at"
        ])
        logger.info(
            "payout.admin.mark_paid payout_id=%s landlord_id=%s marked_by=%s",
            payout.id, payout.landlord_id, request.user.id,
        )
        # Roll the original REQUEST ledger row up to PAID and write the PAID
        # event in one go so the audit history is unambiguous.
        LedgerTransaction.objects.filter(
            user=payout.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
            reference_text__startswith=f"payout:{payout.id}",
        ).update(status=LedgerTransaction.STATUS_PAID)
        LedgerTransaction.objects.create(
            user=payout.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_PAID,
            amount=payout.amount,
            status=LedgerTransaction.STATUS_PAID,
            reference_text=f"payout:{payout.id};marked_by:{request.user.id}",
        )
        return Response({"detail": "Payout marked paid"})


class LandlordPayoutReverseView(APIView):
    """Admin-only endpoint to mark a PROCESSING payout REVERSED.

    Use this when the operator has confirmed off-platform (e.g. through the
    IntaSend dashboard or a bank statement) that the transfer did not
    settle. Releases the reservation and writes a REJECTED ledger row.
    """

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Admin only endpoint"}, status=403)
        payout = LandlordPayout.objects.select_for_update().filter(pk=pk).first()
        if not payout:
            return Response({"detail": "Payout not found"}, status=404)
        if payout.status == LandlordPayout.STATUS_REVERSED:
            return Response({"detail": "Payout already reversed."}, status=400)
        if payout.status not in (LandlordPayout.STATUS_PROCESSING, LandlordPayout.STATUS_REQUESTED):
            return Response(
                {
                    "detail": "Only PROCESSING or REQUESTED payouts can be reversed.",
                    "code": "invalid_state",
                    "current_status": payout.status,
                },
                status=400,
            )
        now = timezone.now()
        payout.status = LandlordPayout.STATUS_REVERSED
        payout.reversed_at = now
        payout.save(update_fields=["status", "reversed_at"])
        # Restore funds under the balance row lock.
        balance, _ = LandlordBalance.objects.get_or_create(landlord=payout.landlord)
        balance = LandlordBalance.objects.select_for_update().get(pk=balance.pk)
        balance.available_balance = balance.available_balance + payout.amount
        balance.save(update_fields=["available_balance", "updated_at"])
        LedgerTransaction.objects.filter(
            user=payout.landlord,
            kind=LedgerTransaction.KIND_LANDLORD_PAYOUT_REQUEST,
            reference_text__startswith=f"payout:{payout.id}",
        ).update(status=LedgerTransaction.STATUS_REJECTED)
        logger.info(
            "payout.admin.reversed payout_id=%s landlord_id=%s marked_by=%s",
            payout.id, payout.landlord_id, request.user.id,
        )
        return Response({"detail": "Payout reversed."})


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
    payload = {
        "period": period,
        "gross_collected": gross,
        "net_amount": gross,
    }

    all_payments = PaymentTransaction.objects.filter(
        lease__unit__property__landlord=request.user,
        status=PaymentTransaction.STATUS_SUCCESS,
    )
    lifetime_gross = all_payments.aggregate(total=Sum("amount"))[
        "total"] or Decimal("0.00")
    payload["lifetime"] = {
        "gross_collected": lifetime_gross,
        "net_amount": lifetime_gross,
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

    period = request.GET.get(
        "period") or timezone.localdate().strftime("%Y-%m")
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
                    "username": _display_name(lease.tenant),
                    "email": lease.tenant.email,
                    "phone_number": tenant_profile.phone_number if tenant_profile else "",
                },
                "unit": {
                    "property_name": lease.unit.property.name,
                    "unit_number": lease.unit.unit_number,
                },
                "status": "PARTIAL" if rent_row["status"] == "OVERDUE" and rent_row.get("cumulative_paid_sum", rent_row["paid_sum"]) > 0 else ("UNPAID" if rent_row["status"] == "OVERDUE" else rent_row["status"]),
                "balance": max(rent_row["balance"], Decimal("0.00")),
                "period": period,
            }
        )

    return Response(LandlordFollowupSerializer(rows, many=True).data)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Drop-in replacement for SimpleJWT's /api/token/ view that respects the
    same 5/min throttle our custom login endpoint enforces."""
    throttle_classes = [TokenObtainRateThrottle]


class LogoutView(APIView):
    """Blacklist the supplied refresh token. Idempotent: re-posting a token
    that is already blacklisted simply returns 205. Without this endpoint a
    stolen refresh token stayed valid for up to JWT_REFRESH_DAYS."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token_value = (request.data or {}).get("refresh")
        if not token_value:
            return Response({"detail": "Refresh token is required."}, status=400)
        try:
            RefreshToken(token_value).blacklist()
        except TokenError:
            # Already invalid/blacklisted/expired. Returning 205 keeps the
            # frontend logout idempotent and avoids leaking token-state info.
            return Response(status=205)
        return Response(status=205)
