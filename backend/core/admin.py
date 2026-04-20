from django.contrib import admin

from .models import (
    Document,
    LandlordBalance,
    LandlordPayout,
    LandlordSettings,
    Lease,
    LedgerTransaction,
    MaintenanceRequest,
    ManagerInvite,
    Notification,
    PaymentTransaction,
    Profile,
    Property,
    Tenant,
    TenantInvite,
    Unit,
)

admin.site.site_header = "KRIB Database Admin"
admin.site.site_title = "KRIB Admin"
admin.site.index_title = "Project Records"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone_number", "wallet_available", "wallet_locked", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "phone_number")


@admin.register(LandlordSettings)
class LandlordSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "business_name")
    search_fields = ("user__username", "user__email", "business_name")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "phone")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "landlord", "manager")
    list_filter = ("location",)
    search_fields = ("name", "location", "landlord__username", "manager__username")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("property", "unit_number", "unit_type", "rent_amount", "deposit", "status")
    list_filter = ("status", "unit_type", "property")
    search_fields = ("property__name", "unit_number")


@admin.register(Lease)
class LeaseAdmin(admin.ModelAdmin):
    list_display = ("unit", "tenant", "rent_amount", "start_date", "end_date", "due_day", "status")
    list_filter = ("status", "start_date", "unit__property")
    search_fields = ("tenant__username", "tenant__first_name", "tenant__last_name", "unit__unit_number", "unit__property__name")


@admin.register(TenantInvite)
class TenantInviteAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "property", "unit", "status", "expires_at", "invited_by")
    list_filter = ("status", "property", "expires_at")
    search_fields = ("full_name", "email", "phone", "property__name", "unit__unit_number", "invited_by__username")


@admin.register(ManagerInvite)
class ManagerInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "phone", "created_by", "created_at", "expires_at", "accepted_at", "is_active")
    list_filter = ("is_active", "created_at", "expires_at")
    search_fields = ("email", "phone", "created_by__username")


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "lease",
        "period",
        "amount",
        "payment_method",
        "status",
        "transaction_code",
        "transaction_date",
    )
    list_filter = ("status", "payment_method", "period")
    search_fields = ("tenant__username", "tenant__email", "transaction_code", "mpesa_receipt", "paypal_order_id", "stripe_payment_intent_id")


@admin.register(LandlordBalance)
class LandlordBalanceAdmin(admin.ModelAdmin):
    list_display = ("landlord", "available_balance", "locked_balance", "updated_at")
    search_fields = ("landlord__username", "landlord__email")


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "amount", "status", "reference_text", "created_at", "available_at")
    list_filter = ("kind", "status", "created_at")
    search_fields = ("user__username", "user__email", "reference_text")


@admin.register(LandlordPayout)
class LandlordPayoutAdmin(admin.ModelAdmin):
    list_display = ("landlord", "amount", "method", "destination", "bank_code", "status", "created_at", "paid_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("landlord__username", "landlord__email", "destination", "bank_code")


@admin.register(MaintenanceRequest)
class MaintenanceRequestAdmin(admin.ModelAdmin):
    list_display = ("tenant", "lease", "urgency", "status", "created_at", "updated_at")
    list_filter = ("status", "urgency", "created_at")
    search_fields = ("tenant__username", "tenant__email", "issue", "lease__unit__unit_number", "lease__unit__property__name")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("property", "tenant", "lease", "document_type", "uploaded_by", "upload_date")
    list_filter = ("document_type", "property", "upload_date")
    search_fields = ("property__name", "tenant__username", "tenant__email", "lease__unit__unit_number", "uploaded_by__username", "file_path")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "type", "period", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("user__username", "user__email", "title", "message")
