from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Document,
    LandlordPayout,
    LandlordSettings,
    Lease,
    LedgerTransaction,
    MaintenanceRequest,
    Notification,
    PaymentTransaction,
    Profile,
    Property,
    Tenant,
    TenantInvite,
    Unit,
    ManagerInvite,
    compute_lease_rent_status,
)
from .services import build_lease_agreement_pdf


class LandlordSignupSerializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=200)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[RegexValidator(regex=r"^[0-9+\-()\s]{7,20}$", message="Invalid phone number format.")],
    )
    password = serializers.CharField(write_only=True, min_length=6)


class RegisterSerializer(serializers.Serializer):
    ROLE_CHOICES = [Profile.ROLE_LANDLORD, Profile.ROLE_TENANT]

    email = serializers.EmailField()
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[RegexValidator(regex=r"^[0-9+\-()\s]{7,20}$", message="Invalid phone number format.")],
    )
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)


class LandlordRevenueSerializer(serializers.Serializer):
    period = serializers.CharField(allow_null=True)
    gross_collected = serializers.DecimalField(max_digits=12, decimal_places=2)
    net_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    lifetime = serializers.DictField()


class LandlordReceiptSerializer(serializers.ModelSerializer):
    tenant = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "mpesa_receipt",
            "tenant",
            "unit",
            "amount",
            "period",
            "status",
            "created_at",
        ]

    def get_tenant(self, obj):
        return {"username": obj.tenant.get_full_name() or obj.tenant.username, "email": obj.tenant.email}

    def get_unit(self, obj):
        return {
            "unit_number": obj.lease.unit.unit_number,
            "property_name": obj.lease.unit.property.name,
        }


class LandlordFollowupSerializer(serializers.Serializer):
    lease_id = serializers.IntegerField()
    tenant = serializers.DictField()
    unit = serializers.DictField()
    status = serializers.CharField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    period = serializers.CharField()


class UserLiteSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff"]

    def get_username(self, obj):
        return obj.get_full_name() or obj.username


class ProfileSerializer(serializers.ModelSerializer):
    user = UserLiteSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "user", "role", "phone_number", "wallet_available", "wallet_locked"]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[RegexValidator(regex=r"^[0-9+\-()\s]{7,20}$", message="Invalid phone number format.")],
    )


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class ManagerInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagerInvite
        fields = ["token", "email", "phone", "expires_at", "accepted_at", "is_active"]
        read_only_fields = ["token", "accepted_at", "is_active"]


class ManagerInviteAcceptSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        validate_password(value)
        return value


class PropertySerializer(serializers.ModelSerializer):
    landlord = UserLiteSerializer(read_only=True)
    manager = UserLiteSerializer(read_only=True)
    manager_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(profile__role=Profile.ROLE_MANAGER), source="manager", write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = Property
        fields = ["id", "landlord", "manager", "manager_id", "name", "location", "description"]


class UnitSerializer(serializers.ModelSerializer):
    property = PropertySerializer(read_only=True)
    property_id = serializers.PrimaryKeyRelatedField(queryset=Property.objects.all(), source="property", write_only=True)

    class Meta:
        model = Unit
        fields = ["id", "property", "property_id", "unit_number", "unit_type", "rent_amount", "deposit", "status"]


class TenantSerializer(serializers.ModelSerializer):
    user = UserLiteSerializer(read_only=True)

    class Meta:
        model = Tenant
        fields = ["id", "user", "phone"]


class LeaseSerializer(serializers.ModelSerializer):
    unit = UnitSerializer(read_only=True)
    unit_id = serializers.PrimaryKeyRelatedField(queryset=Unit.objects.all(), source="unit", write_only=True)
    tenant = UserLiteSerializer(read_only=True)
    tenant_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(profile__role=Profile.ROLE_TENANT),
        source="tenant",
        write_only=True,
    )
    rent_status = serializers.SerializerMethodField()
    identity_document = serializers.FileField(write_only=True, required=False, allow_null=True)
    tenant_signature = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Lease
        fields = [
            "id",
            "unit",
            "unit_id",
            "tenant",
            "tenant_id",
            "rent_amount",
            "start_date",
            "end_date",
            "due_day",
            "status",
            "rent_status",
            "identity_document",
            "tenant_signature",
        ]

    def get_rent_status(self, obj):
        period = self.context.get("period") if self.context else None
        return compute_lease_rent_status(obj, period=period)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None:
            errors = {}
            if not attrs.get("identity_document"):
                errors["identity_document"] = "Capture the tenant ID or passport before creating the lease."
            if not str(attrs.get("tenant_signature") or "").strip():
                errors["tenant_signature"] = "Capture the tenant signature before creating the lease."
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        identity_document = validated_data.pop("identity_document", None)
        tenant_signature = (validated_data.pop("tenant_signature", "") or "").strip()
        request = self.context.get("request")
        uploaded_by = getattr(request, "user", None)

        try:
            with transaction.atomic():
                lease = Lease.objects.create(**validated_data)
                property_obj = lease.unit.property
                document_owner = uploaded_by or property_obj.landlord

                Document.objects.create(
                    property=property_obj,
                    lease=lease,
                    tenant=lease.tenant,
                    uploaded_by=document_owner,
                    document_type=Document.TYPE_IDENTITY,
                    file_path=identity_document,
                )

                lease_pdf = build_lease_agreement_pdf(lease, signature_data_url=tenant_signature)
                if not lease_pdf:
                    raise serializers.ValidationError({"detail": "Lease agreement generation is currently unavailable."})

                lease_filename, lease_file = lease_pdf
                if getattr(lease_file, "name", "") != lease_filename:
                    lease_file.name = lease_filename
                Document.objects.create(
                    property=property_obj,
                    lease=lease,
                    tenant=lease.tenant,
                    uploaded_by=document_owner,
                    document_type=Document.TYPE_LEASE,
                    file_path=lease_file,
                )
                return lease
        except ValueError as exc:
            raise serializers.ValidationError({"tenant_signature": str(exc)}) from exc


class TenantInviteSerializer(serializers.ModelSerializer):
    invited_by = UserLiteSerializer(read_only=True)
    property_name = serializers.CharField(source="property.name", read_only=True)
    unit_label = serializers.SerializerMethodField()
    expires_at = serializers.DateTimeField(required=False)

    class Meta:
        model = TenantInvite
        fields = [
            "id",
            "token",
            "full_name",
            "email",
            "phone",
            "invited_by",
            "property",
            "property_name",
            "unit",
            "unit_label",
            "status",
            "expires_at",
            "otp_code",
            "otp_expires_at",
        ]
        read_only_fields = ["token", "status"]

    def get_unit_label(self, obj):
        if not obj.unit:
            return None
        return f"{obj.unit.property.name} / {obj.unit.unit_number}"

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError({"detail": "Provide at least an email address or phone number."})
        unit = attrs.get("unit")
        property_obj = attrs.get("property")
        if unit and property_obj and unit.property_id != property_obj.id:
            raise serializers.ValidationError({"unit": "Selected unit does not belong to the selected property."})
        if unit and not property_obj:
            attrs["property"] = unit.property
        if not attrs.get("expires_at"):
            attrs["expires_at"] = timezone.now() + timedelta(days=7)
        return attrs


class InviteAcceptSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    identity_document = serializers.FileField(required=False, allow_null=True)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    lease = LeaseSerializer(read_only=True)
    lease_id = serializers.PrimaryKeyRelatedField(queryset=Lease.objects.all(), source="lease", write_only=True, required=False)
    tenant = UserLiteSerializer(read_only=True)
    remaining_balance = serializers.SerializerMethodField()

    def get_remaining_balance(self, obj):
        lease = getattr(obj, "lease", None)
        if not lease:
            return None
        return compute_lease_rent_status(lease, period=obj.period).get("balance")

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "lease",
            "lease_id",
            "tenant",
            "period",
            "billing_period",
            "phone_number",
            "amount",
            "payment_method",
            "transaction_code",
            "merchant_request_id",
            "checkout_request_id",
            "paypal_order_id",
            "stripe_payment_intent_id",
            "status",
            "mpesa_receipt",
            "receipt_file",
            "result_code",
            "result_desc",
            "transaction_date",
            "raw_callback",
            "created_at",
            "remaining_balance",
        ]
        read_only_fields = [
            "merchant_request_id",
            "checkout_request_id",
            "status",
            "mpesa_receipt",
            "transaction_code",
            "receipt_file",
            "result_code",
            "result_desc",
            "transaction_date",
            "raw_callback",
            "created_at",
            "remaining_balance",
        ]


class STKInitiateSerializer(serializers.Serializer):
    lease_id = serializers.PrimaryKeyRelatedField(queryset=Lease.objects.filter(status=Lease.STATUS_ACTIVE), source="lease")
    phone_number = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    tenant = UserLiteSerializer(read_only=True)
    lease = LeaseSerializer(read_only=True)
    lease_id = serializers.PrimaryKeyRelatedField(queryset=Lease.objects.filter(status=Lease.STATUS_ACTIVE), source="lease", write_only=True)

    class Meta:
        model = MaintenanceRequest
        fields = ["id", "tenant", "lease", "lease_id", "issue", "urgency", "photo_path", "status", "created_at", "updated_at"]


class DocumentSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source="property.name", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    tenant_name = serializers.SerializerMethodField()
    unit_label = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "property",
            "property_name",
            "lease",
            "tenant",
            "tenant_name",
            "unit_label",
            "uploaded_by",
            "uploaded_by_name",
            "document_type",
            "file_path",
            "file_name",
            "upload_date",
        ]
        read_only_fields = ["uploaded_by", "upload_date"]

    def validate(self, attrs):
        property_obj = attrs.get("property")
        lease = attrs.get("lease")
        tenant = attrs.get("tenant")
        if lease and property_obj and lease.unit.property_id != property_obj.id:
            raise serializers.ValidationError({"lease": "Selected lease does not belong to the selected property."})
        if tenant and lease and lease.tenant_id != tenant.id:
            raise serializers.ValidationError({"tenant": "Selected tenant does not match the chosen lease."})
        return attrs

    def get_unit_label(self, obj):
        if not obj.lease or not getattr(obj.lease, "unit", None):
            return None
        return f"{obj.lease.unit.property.name} / {obj.lease.unit.unit_number}"

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by:
            return None
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.username

    def get_tenant_name(self, obj):
        if not obj.tenant:
            return None
        return obj.tenant.get_full_name() or obj.tenant.username

    def get_file_name(self, obj):
        if not obj.file_path:
            return None
        return obj.file_path.name.split("/")[-1]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"


class NotificationSendSerializer(serializers.Serializer):
    AUDIENCE_TENANTS = "tenants"
    AUDIENCE_MANAGERS = "managers"
    AUDIENCE_LANDLORDS = "landlords"
    AUDIENCE_EVERYONE = "everyone"
    AUDIENCE_CHOICES = [
        (AUDIENCE_EVERYONE, "Everyone"),
        (AUDIENCE_TENANTS, "Tenants"),
        (AUDIENCE_MANAGERS, "Managers"),
        (AUDIENCE_LANDLORDS, "Landlords"),
    ]

    title = serializers.CharField(max_length=200)
    message = serializers.CharField()
    audience = serializers.ChoiceField(choices=AUDIENCE_CHOICES)
    property_id = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(),
        source="property",
        required=False,
        allow_null=True,
    )
    send_in_app = serializers.BooleanField(required=False, default=True)
    send_email = serializers.BooleanField(required=False, default=False)
    send_sms = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not any([attrs.get("send_in_app", True), attrs.get("send_email", False), attrs.get("send_sms", False)]):
            raise serializers.ValidationError({"detail": "Select at least one delivery channel."})
        return attrs


class LeaseTenantContactSerializer(serializers.Serializer):
    CHANNEL_EMAIL = "email"
    CHANNEL_SMS = "sms"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SMS, "SMS"),
    ]

    channel = serializers.ChoiceField(choices=CHANNEL_CHOICES)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True)
    message = serializers.CharField()


class DashboardRowSerializer(serializers.Serializer):
    lease_id = serializers.IntegerField()
    tenant = serializers.CharField()
    unit = serializers.CharField()
    rent_due = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_sum = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()


class LedgerTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerTransaction
        fields = ["id", "kind", "amount", "status", "available_at", "reference_text", "created_at"]


class WalletWithdrawSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class LandlordPayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = LandlordPayout
        fields = ["id", "amount", "method", "destination", "status", "created_at", "paid_at"]


class LandlordPayoutRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.ChoiceField(choices=[LandlordPayout.METHOD_MPESA, LandlordPayout.METHOD_BANK])
    destination = serializers.CharField(max_length=255)
