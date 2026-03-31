from rest_framework.permissions import BasePermission

from .models import Document, Lease, MaintenanceRequest, PaymentTransaction, Profile, Property


def get_role(user):
    if not user or not user.is_authenticated:
        return None
    profile, _ = Profile.objects.get_or_create(user=user)
    return profile.role


def resolve_property(obj):
    if isinstance(obj, Property):
        return obj
    if isinstance(obj, Lease):
        return obj.unit.property
    if isinstance(obj, MaintenanceRequest):
        return obj.lease.unit.property
    if isinstance(obj, PaymentTransaction):
        return obj.lease.unit.property
    if isinstance(obj, Document):
        return obj.property
    return getattr(obj, "property", None)


class IsLandlord(BasePermission):
    message = "Unauthorized request."

    def has_permission(self, request, view):
        return request.user.is_authenticated and get_role(request.user) == Profile.ROLE_LANDLORD


class IsTenant(BasePermission):
    message = "Unauthorized request."

    def has_permission(self, request, view):
        return request.user.is_authenticated and get_role(request.user) == Profile.ROLE_TENANT


class IsPropertyOwner(BasePermission):
    message = "Unauthorized request."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        prop = resolve_property(obj)
        return bool(prop and prop.landlord_id == request.user.id)


class IsTenantOfProperty(BasePermission):
    message = "Unauthorized request."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        prop = resolve_property(obj)
        if not prop:
            return False
        return Lease.objects.filter(
            tenant=request.user,
            unit__property=prop,
            status=Lease.STATUS_ACTIVE,
        ).exists()
