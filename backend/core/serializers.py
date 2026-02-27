from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Lease,
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


class UserLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class ProfileSerializer(serializers.ModelSerializer):
    user = UserLiteSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "user", "role", "phone_number"]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
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
    lease_id = serializers.PrimaryKeyRelatedField(queryset=Lease.objects.all(), source="lease", write_only=True)
    tenant = UserLiteSerializer(read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = "__all__"
        read_only_fields = [
            "merchant_request_id",
            "checkout_request_id",
            "status",
            "mpesa_receipt",
            "result_code",
            "result_desc",
            "transaction_date",
            "raw_callback",
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
