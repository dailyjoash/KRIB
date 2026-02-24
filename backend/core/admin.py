from django.contrib import admin

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
)

admin.site.register(Profile)
admin.site.register(Tenant)
admin.site.register(Property)
admin.site.register(Unit)
admin.site.register(Lease)
admin.site.register(TenantInvite)
admin.site.register(PaymentTransaction)
admin.site.register(MaintenanceRequest)
admin.site.register(Notification)
