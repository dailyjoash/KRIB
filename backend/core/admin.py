from django.contrib import admin, messages

from .models import (
    CustodyAuditLog,
    Document,
    LandlordBalance,
    LandlordCollectionAccount,
    LandlordPayout,
    LandlordSettings,
    Lease,
    LedgerTransaction,
    MaintenanceRequest,
    ManagerInvite,
    Notification,
    PaymentRecord,
    PaymentRecordAuditLog,
    PaymentTransaction,
    Profile,
    Property,
    SubscriptionInvoice,
    SubscriptionInvoiceAuditLog,
    SubscriptionInvoiceLineItem,
    Tenant,
    TenantInvite,
    Unit,
)
from .services import CustodyCutoverError, switch_landlord_to_direct_paybill, waive_subscription_invoice

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
    list_display = ("user", "business_name", "collection_mode")
    list_filter = ("collection_mode",)
    search_fields = ("user__username", "user__email", "business_name")

    def save_model(self, request, obj, form, change):
        # Cutover safety rail (Phase 2A): a switch to direct_paybill via the
        # admin form must go through the same guard as the API, so an operator
        # cannot accidentally strand a landlord's custody balance. We persist
        # any other edited fields with the PRIOR collection_mode, then run the
        # guarded switch, which either flips the mode + writes an audit row or
        # blocks and leaves the landlord on their existing mode.
        previous = LandlordSettings.objects.filter(pk=obj.pk).first() if obj.pk else None
        previous_mode = previous.collection_mode if previous else LandlordSettings.COLLECTION_CUSTODY_LEGACY
        is_switch_to_direct = (
            obj.collection_mode == LandlordSettings.COLLECTION_DIRECT_PAYBILL
            and previous_mode != LandlordSettings.COLLECTION_DIRECT_PAYBILL
        )
        if not is_switch_to_direct:
            super().save_model(request, obj, form, change)
            return

        obj.collection_mode = previous_mode
        super().save_model(request, obj, form, change)
        try:
            switch_landlord_to_direct_paybill(obj.user, actor=request.user, note="django admin form")
        except CustodyCutoverError as exc:
            self.message_user(request, exc.detail, level=messages.ERROR)
        else:
            self.message_user(
                request,
                f"{obj.user} switched to direct Paybill.",
                level=messages.SUCCESS,
            )
        obj.refresh_from_db()


@admin.register(LandlordCollectionAccount)
class LandlordCollectionAccountAdmin(admin.ModelAdmin):
    list_display = ("landlord", "collection_method", "paybill_number", "registered_business_name", "verification_status", "verified_at")
    list_filter = ("collection_method", "verification_status")
    search_fields = ("landlord__username", "landlord__email", "paybill_number", "registered_business_name")
    readonly_fields = ("created_at", "updated_at", "verified_at")


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


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_code",
        "tenant",
        "landlord",
        "lease",
        "period",
        "amount",
        "allocated_amount",
        "status",
        "verification_label",
        "transaction_date",
    )
    list_filter = ("status", "source", "period", "collection_account__verification_status")
    search_fields = ("transaction_code", "tenant__username", "tenant__email", "landlord__username", "phone_number")
    readonly_fields = ("created_at", "updated_at", "confirmed_at", "rejected_at")


@admin.register(PaymentRecordAuditLog)
class PaymentRecordAuditLogAdmin(admin.ModelAdmin):
    list_display = ("payment_record", "actor", "action", "old_status", "new_status", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("payment_record__transaction_code", "actor__username", "note")


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


@admin.register(CustodyAuditLog)
class CustodyAuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "landlord", "actor", "available_balance", "locked_balance", "amount", "payout")
    list_filter = ("action", "created_at")
    search_fields = ("landlord__username", "landlord__email", "actor__username", "note")
    readonly_fields = (
        "actor", "landlord", "action", "available_balance",
        "locked_balance", "amount", "payout", "note", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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


class SubscriptionInvoiceLineItemInline(admin.TabularInline):
    model = SubscriptionInvoiceLineItem
    extra = 0
    can_delete = False
    readonly_fields = ("unit", "lease", "unit_label", "lease_status_at_snapshot", "created_at")


@admin.register(SubscriptionInvoice)
class SubscriptionInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "landlord",
        "period",
        "billable_units_count",
        "amount",
        "status",
        "generated_at",
        "paid_at",
    )
    list_filter = ("status", "period")
    search_fields = (
        "landlord__username",
        "landlord__email",
        "period",
        "paid_via",
        "intasend_invoice_id",
    )
    readonly_fields = (
        "landlord",
        "period",
        "billable_units_count",
        "amount",
        "generated_at",
        "due_at",
        "paid_at",
        "paid_via",
        "intasend_invoice_id",
        "payment_reference",
        "payment_initiated_at",
        "created_at",
        "updated_at",
    )
    inlines = [SubscriptionInvoiceLineItemInline]
    actions = ["waive_invoices"]

    @admin.action(description="Waive selected invoices")
    def waive_invoices(self, request, queryset):
        waived = 0
        skipped = 0
        for invoice in queryset:
            ok, _ = waive_subscription_invoice(
                invoice, actor=request.user, note="admin bulk action"
            )
            if ok:
                waived += 1
            else:
                skipped += 1
        self.message_user(
            request,
            f"Waived {waived} invoice(s); skipped {skipped} (already paid/waived).",
            level=messages.SUCCESS if waived else messages.WARNING,
        )


@admin.register(SubscriptionInvoiceAuditLog)
class SubscriptionInvoiceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("invoice", "actor", "action", "old_status", "new_status", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("invoice__landlord__username", "actor__username", "note")
    readonly_fields = ("invoice", "actor", "action", "old_status", "new_status", "note", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
