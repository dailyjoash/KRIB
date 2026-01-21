from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Property, Lease, Payment, Maintenance, Manager, Tenant
from .serializers import (
    PropertySerializer, LeaseSerializer, PaymentSerializer,
    MaintenanceSerializer, ManagerSerializer, TenantSerializer
)

# 👤 Authenticated user info (/auth/me/)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_me(request):
    user = request.user

    # Determine role dynamically
    if user.is_staff:
        role = "landlord"
    elif hasattr(user, 'manager_profile'):
        role = "manager"
    elif hasattr(user, 'tenant_profile'):
        role = "tenant"
    else:
        role = "user"

    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": role
    })

# 🏠 Get all properties (filtered by role)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def properties_list(request):
    user = request.user

    if user.is_staff:  # Landlord
        properties = Property.objects.filter(landlord=user)
    elif hasattr(user, 'manager_profile'):  # Manager
        properties = Property.objects.filter(manager=user.manager_profile)
    elif hasattr(user, 'tenant_profile'):  # Tenant
        properties = Property.objects.filter(leases__tenant=user.tenant_profile)
    else:
        properties = Property.objects.none()

    serializer = PropertySerializer(properties, many=True)
    return Response(serializer.data)

# 📜 Get leases (filtered by role)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def leases_list(request):
    user = request.user

    if user.is_staff:  # Landlord
        leases = Lease.objects.filter(property__landlord=user)
    elif hasattr(user, 'manager_profile'):  # Manager
        leases = Lease.objects.filter(property__manager=user.manager_profile)
    elif hasattr(user, 'tenant_profile'):  # Tenant
        leases = Lease.objects.filter(tenant=user.tenant_profile)
    else:
        leases = Lease.objects.none()

    serializer = LeaseSerializer(leases, many=True)
    return Response(serializer.data)

# 🧾 Get a tenant's own lease (for tenant dashboard)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_lease(request):
    user = request.user

    if hasattr(user, 'tenant_profile'):
        lease = Lease.objects.filter(tenant=user.tenant_profile).first()
        if not lease:
            return Response({"detail": "No active lease found."}, status=404)
        serializer = LeaseSerializer(lease)
        return Response(serializer.data)

    return Response({"detail": "Only tenants can access this endpoint."}, status=403)

# 💰 Get payments (filtered by role)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payments_list(request):
    user = request.user

    if user.is_staff:  # Landlord
        payments = Payment.objects.filter(lease__property__landlord=user)
    elif hasattr(user, 'manager_profile'):
        payments = Payment.objects.filter(lease__property__manager=user.manager_profile)
    elif hasattr(user, 'tenant_profile'):
        payments = Payment.objects.filter(lease__tenant=user.tenant_profile)
    else:
        payments = Payment.objects.none()

    serializer = PaymentSerializer(payments, many=True)
    return Response(serializer.data)

# 🧰 Maintenance (tenant + manager/landlord)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_maintenance(request):
    user = request.user

    if hasattr(user, 'tenant_profile'):
        requests = Maintenance.objects.filter(tenant=user.tenant_profile)
    elif user.is_staff:
        requests = Maintenance.objects.filter(property__landlord=user)
    elif hasattr(user, 'manager_profile'):
        requests = Maintenance.objects.filter(property__manager=user.manager_profile)
    else:
        return Response({"detail": "No maintenance data for this user."}, status=400)

    serializer = MaintenanceSerializer(requests, many=True)
    return Response(serializer.data)