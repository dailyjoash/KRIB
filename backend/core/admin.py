
from django.contrib import admin
from .models import Property, Tenant, Lease, Payment, Maintenance, Manager, Profile, Document, Notification, TenantInvite

admin.site.register(Property)
admin.site.register(Tenant)
admin.site.register(Lease)
admin.site.register(Payment)
admin.site.register(Maintenance)
admin.site.register(Manager)
admin.site.register(Profile)
admin.site.register(Document)
admin.site.register(Notification)


@admin.register(TenantInvite)
class TenantInviteAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "status",
                    "invited_by", "created_at", "expires_at")
    list_filter = ("status", "created_at")
    search_fields = ("full_name", "email", "phone", "invited_by__username")
