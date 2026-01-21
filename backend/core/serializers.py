from rest_framework import serializers
from .models import Property, Lease, Payment, Maintenance, Manager, Tenant


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
    tenant = TenantSerializer(read_only=True)

    class Meta:
        model = Lease
        fields = '__all__'


# 💸 Payment Serializer
class PaymentSerializer(serializers.ModelSerializer):
    lease = LeaseSerializer(read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'


# 🧰 Maintenance Serializer
class MaintenanceSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)
    property = PropertySerializer(read_only=True)

    class Meta:
        model = Maintenance
        fields = '__all__'
