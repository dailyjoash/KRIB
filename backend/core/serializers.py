from rest_framework import serializers
<<<<<<< HEAD
from .models import (
    Property,
    Lease,
    Payment,
    Maintenance,
    Manager,
    Tenant,
    Profile,
    Document,
    Notification,
    TenantInvite,
)
=======
from .models import Property, Lease, Payment, Maintenance, Manager, Tenant, Profile, Document, Notification
>>>>>>> origin/master


# 👤 Profile Serializer
class ProfileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()

    class Meta:
        model = Profile
        fields = ['id', 'user', 'role']


# 👨‍💼 Manager Serializer
class ManagerSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()
    landlord = serializers.StringRelatedField()

    class Meta:
        model = Manager
        fields = ['id', 'user', 'landlord']


# 🧍 Tenant Serializer
class TenantSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()

    class Meta:
        model = Tenant
        fields = ['id', 'user', 'phone', 'national_id']


# 🏠 Property Serializer
class PropertySerializer(serializers.ModelSerializer):
    landlord = serializers.StringRelatedField()
    manager = ManagerSerializer(read_only=True)

    class Meta:
        model = Property
        fields = '__all__'


# 📜 Lease Serializer
class LeaseSerializer(serializers.ModelSerializer):
    property = PropertySerializer(read_only=True)
    property_id = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(),
        source="property",
        write_only=True,
        required=False,
    )
    tenant = TenantSerializer(read_only=True)
    tenant_id = serializers.PrimaryKeyRelatedField(
        queryset=Tenant.objects.all(),
        source="tenant",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Lease
        fields = '__all__'


# 💸 Payment Serializer
class PaymentSerializer(serializers.ModelSerializer):
    lease = LeaseSerializer(read_only=True)
    lease_id = serializers.PrimaryKeyRelatedField(
        queryset=Lease.objects.all(),
        source="lease",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Payment
        fields = '__all__'


# 🧰 Maintenance Serializer
class MaintenanceSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)
    tenant_id = serializers.PrimaryKeyRelatedField(
        queryset=Tenant.objects.all(),
        source="tenant",
        write_only=True,
        required=False,
    )
    property = PropertySerializer(read_only=True)
    property_id = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(),
        source="property",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Maintenance
        fields = '__all__'


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Document
        fields = '__all__'


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
<<<<<<< HEAD


class TenantInviteSerializer(serializers.ModelSerializer):
    invited_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = TenantInvite
        fields = '__all__'
        extra_kwargs = {
            "token": {"read_only": True},
            "invited_by": {"read_only": True},
            "created_at": {"read_only": True},
            "expires_at": {"read_only": True},
            "status": {"read_only": True},
            "otp_code": {"read_only": True},
            "otp_expires_at": {"read_only": True},
        }

    def validate(self, attrs):
        email = attrs.get("email")
        phone = attrs.get("phone")
        if not email and not phone:
            raise serializers.ValidationError("Email or phone is required.")
        return attrs
=======
>>>>>>> origin/master
