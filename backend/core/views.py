from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from .models import (
    Property,
    Lease,
    Payment,
    Maintenance,
    Manager,
    Tenant,
    Document,
    Notification,
)
from .serializers import (
    PropertySerializer,
    LeaseSerializer,
    PaymentSerializer,
    MaintenanceSerializer,
    ManagerSerializer,
    TenantSerializer,
    DocumentSerializer,
    NotificationSerializer,
)

# 👤 Authenticated user info (/auth/me/)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_me(request):
    user = request.user

    # Determine role dynamically
    if hasattr(user, "profile"):
        role = user.profile.role
    elif user.is_staff:
        role = "landlord"
    elif hasattr(user, "manager_profile"):
        role = "manager"
    elif hasattr(user, "tenant_profile"):
        role = "tenant"
    else:
        role = "user"

    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": role
    })

def _get_role(user):
    if hasattr(user, "profile"):
        return user.profile.role
    if user.is_staff:
        return "landlord"
    if hasattr(user, "manager_profile"):
        return "manager"
    if hasattr(user, "tenant_profile"):
        return "tenant"
    return "user"


class PropertyViewSet(viewsets.ModelViewSet):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == "landlord":
            return Property.objects.filter(landlord=user)
        if role == "manager" and hasattr(user, "manager_profile"):
            return Property.objects.filter(manager=user.manager_profile)
        if role == "tenant" and hasattr(user, "tenant_profile"):
            return Property.objects.filter(leases__tenant=user.tenant_profile)
        return Property.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = _get_role(user)
        if role == "landlord":
            serializer.save(landlord=user)
            return
        if role == "manager" and hasattr(user, "manager_profile"):
            serializer.save(landlord=user.manager_profile.landlord, manager=user.manager_profile)
            return
        raise PermissionDenied("Only landlords or managers can create properties.")


class LeaseViewSet(viewsets.ModelViewSet):
    serializer_class = LeaseSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == "landlord":
            return Lease.objects.filter(property__landlord=user)
        if role == "manager" and hasattr(user, "manager_profile"):
            return Lease.objects.filter(property__manager=user.manager_profile)
        if role == "tenant" and hasattr(user, "tenant_profile"):
            return Lease.objects.filter(tenant=user.tenant_profile)
        return Lease.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = _get_role(user)
        if role not in {"landlord", "manager"}:
            raise PermissionDenied("Only landlords or managers can create leases.")
        property_id = self.request.data.get("property")
        tenant_id = self.request.data.get("tenant")
        if not property_id or not tenant_id:
            raise ValidationError("Property and tenant are required.")
        try:
            prop = Property.objects.get(id=property_id)
        except Property.DoesNotExist as exc:
            raise ValidationError("Property not found.") from exc
        if role == "landlord" and prop.landlord != user:
            raise PermissionDenied("You do not own this property.")
        if role == "manager" and prop.manager != user.manager_profile:
            raise PermissionDenied("You are not assigned to this property.")
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist as exc:
            raise ValidationError("Tenant not found.") from exc
        if Lease.objects.filter(property=prop, is_active=True).exists():
            raise ValidationError("An active lease already exists for this property.")
        serializer.save(property=prop, tenant=tenant)

    @action(detail=True, methods=["post"])
    def end_lease(self, request, pk=None):
        lease = self.get_object()
        lease.is_active = False
        lease.save()
        return Response({"detail": "Lease ended."})

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

class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == "landlord":
            return Payment.objects.filter(lease__property__landlord=user)
        if role == "manager" and hasattr(user, "manager_profile"):
            return Payment.objects.filter(lease__property__manager=user.manager_profile)
        if role == "tenant" and hasattr(user, "tenant_profile"):
            return Payment.objects.filter(lease__tenant=user.tenant_profile)
        return Payment.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = _get_role(user)
        lease_id = self.request.data.get("lease")
        if not lease_id:
            raise ValidationError("Lease is required.")
        try:
            lease = Lease.objects.get(id=lease_id)
        except Lease.DoesNotExist as exc:
            raise ValidationError("Lease not found.") from exc
        if not lease.is_active:
            raise ValidationError("Lease is not active.")
        amount = serializer.validated_data.get("amount")
        if amount != lease.rent_amount:
            raise ValidationError("Payment amount must match rent amount.")
        if role == "tenant":
            if not hasattr(user, "tenant_profile") or lease.tenant != user.tenant_profile:
                raise PermissionDenied("You can only pay for your own lease.")
        serializer.save(lease=lease, status="Paid")
        Notification.objects.create(
            user=lease.property.landlord,
            title="Rent payment received",
            message=f"{lease.tenant.user.username} paid {amount} KES for {lease.property.title}.",
        )
        Notification.objects.create(
            user=lease.tenant.user,
            title="Payment successful",
            message=f"Your payment of {amount} KES for {lease.property.title} was received.",
        )


class MaintenanceViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == "tenant" and hasattr(user, "tenant_profile"):
            return Maintenance.objects.filter(tenant=user.tenant_profile)
        if role == "landlord":
            return Maintenance.objects.filter(property__landlord=user)
        if role == "manager" and hasattr(user, "manager_profile"):
            return Maintenance.objects.filter(property__manager=user.manager_profile)
        return Maintenance.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = _get_role(user)
        if role != "tenant":
            raise PermissionDenied("Only tenants can submit maintenance requests.")
        property_id = self.request.data.get("property")
        if not property_id:
            raise ValidationError("Property is required.")
        try:
            prop = Property.objects.get(id=property_id)
        except Property.DoesNotExist as exc:
            raise ValidationError("Property not found.") from exc
        has_active_lease = Lease.objects.filter(
            tenant=user.tenant_profile,
            property=prop,
            is_active=True,
        ).exists()
        if not has_active_lease:
            raise ValidationError("You need an active lease for this property.")
        serializer.save(tenant=user.tenant_profile, property=prop, status="Pending")
        Notification.objects.create(
            user=prop.landlord,
            title="New maintenance request",
            message=f"{user.username} reported an issue at {prop.title}.",
        )

    def perform_update(self, serializer):
        user = self.request.user
        role = _get_role(user)
        if role == "tenant":
            raise PermissionDenied("Tenants cannot update maintenance status.")
        serializer.save()


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        role = _get_role(user)
        if role == "landlord":
            return Document.objects.filter(property__landlord=user)
        if role == "manager" and hasattr(user, "manager_profile"):
            return Document.objects.filter(property__manager=user.manager_profile)
        if role == "tenant" and hasattr(user, "tenant_profile"):
            return Document.objects.filter(lease__tenant=user.tenant_profile)
        return Document.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = _get_role(user)
        property_id = self.request.data.get("property")
        if not property_id:
            raise ValidationError("Property is required.")
        try:
            prop = Property.objects.get(id=property_id)
        except Property.DoesNotExist as exc:
            raise ValidationError("Property not found.") from exc
        if role == "landlord" and prop.landlord != user:
            raise PermissionDenied("You do not own this property.")
        if role == "manager" and prop.manager != user.manager_profile:
            raise PermissionDenied("You are not assigned to this property.")
        if role == "tenant":
            lease_id = self.request.data.get("lease")
            if not lease_id:
                raise ValidationError("Lease is required for tenant uploads.")
            lease = Lease.objects.get(id=lease_id)
            if lease.tenant != user.tenant_profile:
                raise PermissionDenied("You cannot upload documents for this lease.")
            if lease.property != prop:
                raise ValidationError("Lease does not match the selected property.")
            serializer.save(uploaded_by=user, property=prop, lease=lease)
            return
        serializer.save(uploaded_by=user, property=prop)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")
