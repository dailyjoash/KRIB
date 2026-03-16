from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from rest_framework import serializers

from .models import (
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


class LandlordSignupSerializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=200)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[RegexValidator(regex=r"^[0-9+\-()\s]{7,20}$", message="Invalid phone number format.")],
    )
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value


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
        return {"username": obj.tenant.username, "email": obj.tenant.email}

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
    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff"]


class ProfileSerializer(serializers.ModelSerializer):
    user = UserLiteSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "user", "role", "phone_number", "wallet_available", "wallet_locked"]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
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


class ManagerInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagerInvite
        fields = ["token", "email", "phone", "expires_at", "accepted_at", "is_active"]
        read_only_fields = ["token", "accepted_at", "is_active"]


class ManagerInviteAcceptSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        validate_password(value)
        return value


class PropertySerializer(serializers.ModelSerializer):
    landlord = UserLiteSerializer(read_only=True)
    manager = UserLiteSerializer(read_only=True)
    manager_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="manager", write_only=True, required=False, allow_null=True
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
    tenant_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source="tenant", write_only=True)
    rent_status = serializers.SerializerMethodField()

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
            "due_day",
            "status",
            "rent_status",
        ]

    def get_rent_status(self, obj):
        period = self.context.get("period") if self.context else None
        return compute_lease_rent_status(obj, period=period)


class TenantInviteSerializer(serializers.ModelSerializer):
    invited_by = UserLiteSerializer(read_only=True)

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
            "unit",
            "status",
            "expires_at",
            "otp_code",
            "otp_expires_at",
        ]
        read_only_fields = ["token", "status"]


class InviteAcceptSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=6)
    username = serializers.CharField(required=False)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    lease = LeaseSerializer(read_only=True)
    lease_id = serializers.PrimaryKeyRelatedField(queryset=Lease.objects.all(), source="lease", write_only=True, required=False)
    tenant = UserLiteSerializer(read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "lease",
            "lease_id",
            "tenant",
            "period",
            "phone_number",
            "amount",
            "merchant_request_id",
            "checkout_request_id",
            "status",
            "mpesa_receipt",
            "result_code",
            "result_desc",
            "transaction_date",
            "raw_callback",
            "created_at",
        ]
        read_only_fields = [
            "merchant_request_id",
            "checkout_request_id",
            "status",
            "mpesa_receipt",
            "result_code",
            "result_desc",
            "transaction_date",
            "raw_callback",
            "created_at",
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
        fields = ["id", "tenant", "lease", "lease_id", "issue", "status", "created_at", "updated_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"


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
