import random
import uuid
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _random_reference(length=5):
    return "".join(random.choice(_REFERENCE_ALPHABET) for _ in range(length))


class Profile(models.Model):
    ROLE_LANDLORD = "landlord"
    ROLE_MANAGER = "manager"
    ROLE_TENANT = "tenant"
    ROLE_CHOICES = [
        (ROLE_LANDLORD, "Landlord"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_TENANT, "Tenant"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_TENANT)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    wallet_available = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    wallet_locked = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(wallet_available__gte=Decimal("0.00")),
                name="profile_wallet_available_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(wallet_locked__gte=Decimal("0.00")),
                name="profile_wallet_locked_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class LandlordSettings(models.Model):
    COLLECTION_CUSTODY_LEGACY = "custody_legacy"
    COLLECTION_DIRECT_PAYBILL = "direct_paybill"
    COLLECTION_MODE_CHOICES = [
        (COLLECTION_CUSTODY_LEGACY, "KRIB custody legacy"),
        (COLLECTION_DIRECT_PAYBILL, "Direct landlord Paybill"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="landlord_settings")
    business_name = models.CharField(max_length=200)
    collection_mode = models.CharField(
        max_length=30,
        choices=COLLECTION_MODE_CHOICES,
        default=COLLECTION_CUSTODY_LEGACY,
    )
    payout_method = models.CharField(max_length=20, blank=True, null=True)
    payout_destination = models.CharField(max_length=255, blank=True, null=True)
    payout_bank_code = models.CharField(max_length=50, blank=True, null=True)
    # Updated by the settings serializer whenever the payout destination/method
    # changes. The payout view refuses to release funds while this is recent
    # so a hijacked session that pivots through settings has a forced wait.
    payout_destination_updated_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.business_name} ({self.user.username})"


class LandlordCollectionAccount(models.Model):
    METHOD_MPESA_PAYBILL = "mpesa_paybill"
    METHOD_CHOICES = [
        (METHOD_MPESA_PAYBILL, "M-Pesa Paybill"),
    ]

    STATUS_UNVERIFIED = "unverified"
    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_UNVERIFIED, "Unverified"),
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_REJECTED, "Rejected"),
    ]

    landlord = models.OneToOneField(User, on_delete=models.CASCADE, related_name="collection_account")
    collection_method = models.CharField(max_length=30, choices=METHOD_CHOICES, default=METHOD_MPESA_PAYBILL)
    paybill_number = models.CharField(max_length=20)
    registered_business_name = models.CharField(max_length=200)
    verification_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verification_notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="verified_collection_accounts",
    )
    # Placeholder only. Phase 1 does not register or consume per-landlord C2B callbacks.
    callback_status = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["paybill_number"], name="uniq_landlord_collection_paybill"),
        ]

    def clean(self):
        if self.collection_method != self.METHOD_MPESA_PAYBILL:
            raise ValidationError("Only M-Pesa Paybill collection accounts are supported.")
        if not str(self.paybill_number or "").isdigit():
            raise ValidationError("Paybill number must contain digits only.")

    def save(self, *args, **kwargs):
        if self.pk:
            previous = LandlordCollectionAccount.objects.filter(pk=self.pk).first()
            collection_fields_changed = previous and (
                previous.collection_method != self.collection_method
                or previous.paybill_number != self.paybill_number
                or previous.registered_business_name != self.registered_business_name
            )
            if collection_fields_changed:
                self.verification_status = self.STATUS_PENDING
                self.verified_at = None
                self.verified_by = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.landlord.username} Paybill {self.paybill_number}"


class Tenant(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tenant_profile")
    phone = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.user.username


class Property(models.Model):
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name="properties")
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_properties")
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Unit(models.Model):
    TYPE_SINGLE = "single"
    TYPE_BEDSITTER = "bedsitter"
    TYPE_1BR = "1br"
    TYPE_2BR = "2br"
    TYPE_OTHER = "other"
    UNIT_TYPE_CHOICES = [
        (TYPE_SINGLE, "Single"),
        (TYPE_BEDSITTER, "Bedsitter"),
        (TYPE_1BR, "1BR"),
        (TYPE_2BR, "2BR"),
        (TYPE_OTHER, "Other"),
    ]

    STATUS_VACANT = "vacant"
    STATUS_OCCUPIED = "occupied"
    STATUS_CHOICES = [
        (STATUS_VACANT, "VACANT"),
        (STATUS_OCCUPIED, "OCCUPIED"),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="units")
    unit_number = models.CharField(max_length=50)
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPE_CHOICES, default=TYPE_OTHER)
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_VACANT)

    class Meta:
        unique_together = ("property", "unit_number")
        constraints = [
            # Application code already validates these, but DB-level constraints
            # defend against bypasses via shell-loaded fixtures, raw SQL, or
            # imports that skip Django form/serializer validation.
            models.CheckConstraint(
                condition=models.Q(rent_amount__gte=Decimal("0.00")),
                name="unit_rent_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(deposit__gte=Decimal("0.00")),
                name="unit_deposit_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.property.name} - {self.unit_number}"


class Lease(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "ACTIVE"),
        (STATUS_INACTIVE, "INACTIVE"),
    ]

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name="leases")
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leases")
    rent_amount = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    due_day = models.PositiveSmallIntegerField(default=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    payment_reference = models.CharField(max_length=8, blank=True, null=True, db_index=True)
    payment_reference_landlord = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )
    # Maintained mirror of unit_id while the lease is active (NULL otherwise).
    # Backs the MySQL-compatible "one active lease per unit" unique constraint:
    # two active leases on a unit collide on this key, inactive leases get NULL
    # and NULLs are treated as distinct.
    active_unit_key = models.PositiveIntegerField(null=True, blank=True, editable=False)

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("Lease end date cannot be before the start date.")
        if self.status == self.STATUS_ACTIVE:
            existing = Lease.objects.filter(unit=self.unit, status=self.STATUS_ACTIVE)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError("Only one active lease is allowed per unit.")
            tenant_existing = Lease.objects.filter(
                tenant=self.tenant,
                unit__property=self.unit.property,
                status=self.STATUS_ACTIVE,
            )
            if self.pk:
                tenant_existing = tenant_existing.exclude(pk=self.pk)
            if tenant_existing.exists():
                raise ValidationError("Only one active lease is allowed per tenant per property.")

    def save(self, *args, **kwargs):
        if not self.rent_amount:
            self.rent_amount = self.unit.rent_amount
        if self.unit_id:
            self.payment_reference_landlord = self.unit.property.landlord
        if not self.payment_reference and self.unit_id:
            self.payment_reference = self._generate_payment_reference()
        self.active_unit_key = self.unit_id if self.status == self.STATUS_ACTIVE else None
        self.full_clean()
        super().save(*args, **kwargs)
        self.unit.status = Unit.STATUS_OCCUPIED if self.status == self.STATUS_ACTIVE else Unit.STATUS_VACANT
        self.unit.save(update_fields=["status"])

    def _generate_payment_reference(self):
        landlord = self.unit.property.landlord
        unit_code = "".join(ch for ch in (self.unit.unit_number or "").upper() if ch.isalnum())
        candidates = []
        if 4 <= len(unit_code) <= 6:
            candidates.append(unit_code)
        elif unit_code:
            if len(unit_code) > 6:
                candidates.append(unit_code[:6])
            else:
                suffix_length = max(4 - len(unit_code), 1)
                candidates.append(f"{unit_code}{_random_reference(suffix_length)}")

        for candidate in candidates:
            if not self._payment_reference_exists(landlord, candidate):
                return candidate

        for _ in range(100):
            candidate = _random_reference(5)
            if not self._payment_reference_exists(landlord, candidate):
                return candidate
        raise ValidationError("Could not generate a unique payment reference.")

    def _payment_reference_exists(self, landlord, reference):
        qs = Lease.objects.filter(payment_reference_landlord=landlord, payment_reference=reference)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        return qs.exists()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rent_amount__gte=Decimal("0.00")),
                name="lease_rent_amount_non_negative",
            ),
            models.CheckConstraint(
                # Months only have 28-31 days; 28 is the safest universal cap.
                # `due_day` is also a PositiveSmallIntegerField so the >= 1
                # half is enforced by the column type.
                condition=models.Q(due_day__gte=1) & models.Q(due_day__lte=28),
                name="lease_due_day_in_range",
            ),
            # At most one ACTIVE lease per unit. Enforced through the maintained
            # `active_unit_key` mirror column so this stays a plain unique
            # constraint (MySQL has no partial/conditional unique constraints).
            # The application-side check in `clean()` still runs (with a
            # friendly error) and there is also `tenant+property` enforcement
            # there, but this guarantees the invariant even against raw SQL.
            models.UniqueConstraint(
                fields=["active_unit_key"],
                name="lease_one_active_per_unit",
            ),
            # Payment references are unique per landlord. Unset references are
            # stored as NULL (not "") so this is a plain unique constraint:
            # MySQL treats NULLs as distinct, so multiple unset references
            # coexist while real values stay unique per landlord.
            models.UniqueConstraint(
                fields=["payment_reference_landlord", "payment_reference"],
                name="lease_unique_payment_reference_per_landlord",
            ),
        ]

    def __str__(self):
        return f"Lease {self.unit} - {self.tenant.username}"


class TenantInvite(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "PENDING"),
        (STATUS_ACCEPTED, "ACCEPTED"),
        (STATUS_EXPIRED, "EXPIRED"),
        (STATUS_CANCELLED, "CANCELLED"),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_invites")
    property = models.ForeignKey(Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="invites")
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="invites")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    expires_at = models.DateTimeField()
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    otp_locked = models.BooleanField(default=False)
    otp_expires_at = models.DateTimeField(blank=True, null=True)

    def is_expired(self):
        return timezone.now() > self.expires_at


class ManagerInvite(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="manager_invites")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def is_expired(self):
        return timezone.now() > self.expires_at


class PaymentTransaction(models.Model):
    METHOD_MPESA = "mpesa"
    METHOD_CARD = "card"
    METHOD_PAYPAL = "paypal"
    METHOD_CHOICES = [
        (METHOD_MPESA, "M-Pesa"),
        (METHOD_CARD, "Card"),
        (METHOD_PAYPAL, "PayPal"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "PENDING"),
        (STATUS_SUCCESS, "SUCCESS"),
        (STATUS_FAILED, "FAILED"),
    ]

    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="payment_transactions")
    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_transactions")
    period = models.CharField(max_length=7)
    billing_period = models.DateField(blank=True, null=True)
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_MPESA)
    transaction_code = models.CharField(max_length=100, unique=True, blank=True, null=True)
    merchant_request_id = models.CharField(max_length=100, blank=True, null=True)
    checkout_request_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    paypal_order_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    mpesa_receipt = models.CharField(max_length=100, blank=True, null=True)
    result_code = models.IntegerField(blank=True, null=True)
    result_desc = models.CharField(max_length=255, blank=True, null=True)
    receipt_file = models.FileField(upload_to="receipts/", blank=True, null=True)
    transaction_date = models.DateTimeField(blank=True, null=True)
    raw_callback = models.JSONField(blank=True, null=True)
    allocation_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="paymenttransaction_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.tenant.username} {self.period} {self.amount}"


class PaymentRecord(models.Model):
    STATUS_PENDING_CONFIRMATION = "pending_confirmation"
    STATUS_CONFIRMED = "confirmed"
    STATUS_REJECTED = "rejected"
    STATUS_UNMATCHED = "unmatched"
    STATUS_DISPUTED = "disputed"
    STATUS_CHOICES = [
        (STATUS_PENDING_CONFIRMATION, "Pending confirmation"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_UNMATCHED, "Unmatched"),
        (STATUS_DISPUTED, "Disputed"),
    ]

    SOURCE_DIRECT_PAYBILL = "direct_paybill"
    SOURCE_CHOICES = [
        (SOURCE_DIRECT_PAYBILL, "Direct landlord Paybill"),
    ]

    lease = models.ForeignKey(Lease, on_delete=models.SET_NULL, blank=True, null=True, related_name="direct_payment_records")
    tenant = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="direct_payment_records")
    landlord = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="landlord_direct_payment_records")
    collection_account = models.ForeignKey(
        LandlordCollectionAccount,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="payment_records",
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_DIRECT_PAYBILL)
    period = models.CharField(max_length=7)
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    transaction_code = models.CharField(max_length=100, unique=True)
    transaction_date = models.DateTimeField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING_CONFIRMATION)
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="submitted_direct_payment_records",
    )
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="confirmed_direct_payment_records",
    )
    rejected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="rejected_direct_payment_records",
    )
    confirmation_note = models.TextField(blank=True)
    rejection_note = models.TextField(blank=True)
    flagged_reason = models.CharField(max_length=255, blank=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)
    rejected_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="paymentrecord_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gte=Decimal("0.00")),
                name="paymentrecord_allocated_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_amount__lte=models.F("amount")),
                name="paymentrecord_allocated_lte_amount",
            ),
        ]

    @property
    def verification_label(self):
        if self.collection_account and self.collection_account.verification_status == LandlordCollectionAccount.STATUS_VERIFIED:
            return "verified_landlord_collected"
        return "tenant_reported_unverified"

    def __str__(self):
        return f"{self.transaction_code} {self.amount} {self.status}"


class PaymentRecordAuditLog(models.Model):
    ACTION_SUBMIT = "submit"
    ACTION_CONFIRM = "confirm"
    ACTION_REJECT = "reject"
    ACTION_ATTACH = "attach"
    ACTION_CHOICES = [
        (ACTION_SUBMIT, "Submit"),
        (ACTION_CONFIRM, "Confirm"),
        (ACTION_REJECT, "Reject"),
        (ACTION_ATTACH, "Attach"),
    ]

    payment_record = models.ForeignKey(PaymentRecord, on_delete=models.CASCADE, related_name="audit_logs")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="direct_payment_audit_logs")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class LandlordBalance(models.Model):
    landlord = models.OneToOneField(User, on_delete=models.CASCADE, related_name="landlord_balance")
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    locked_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(available_balance__gte=Decimal("0.00")),
                name="landlordbalance_available_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(locked_balance__gte=Decimal("0.00")),
                name="landlordbalance_locked_non_negative",
            ),
        ]


class LedgerTransaction(models.Model):
    KIND_WALLET_CREDIT = "WALLET_CREDIT"
    KIND_WALLET_DEBIT_RENT = "WALLET_DEBIT_RENT"
    KIND_WALLET_WITHDRAW_REQUEST = "WALLET_WITHDRAW_REQUEST"
    KIND_WALLET_WITHDRAW_PAID = "WALLET_WITHDRAW_PAID"
    KIND_LANDLORD_CREDIT_RENT = "LANDLORD_CREDIT_RENT"
    KIND_LANDLORD_PAYOUT_REQUEST = "LANDLORD_PAYOUT_REQUEST"
    KIND_LANDLORD_PAYOUT_PAID = "LANDLORD_PAYOUT_PAID"
    KIND_CHOICES = [
        (KIND_WALLET_CREDIT, "Wallet Credit"),
        (KIND_WALLET_DEBIT_RENT, "Wallet Debit Rent"),
        (KIND_WALLET_WITHDRAW_REQUEST, "Wallet Withdrawal Request"),
        (KIND_WALLET_WITHDRAW_PAID, "Wallet Withdrawal Paid"),
        (KIND_LANDLORD_CREDIT_RENT, "Landlord Credit Rent"),
        (KIND_LANDLORD_PAYOUT_REQUEST, "Landlord Payout Request"),
        (KIND_LANDLORD_PAYOUT_PAID, "Landlord Payout Paid"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_LOCKED = "LOCKED"
    STATUS_AVAILABLE = "AVAILABLE"
    STATUS_PAID = "PAID"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_AVAILABLE, "Available"),
        (STATUS_PAID, "Paid"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ledger_transactions")
    kind = models.CharField(max_length=40, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    available_at = models.DateTimeField(blank=True, null=True)
    reference_text = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LandlordPayout(models.Model):
    METHOD_MPESA = "MPESA"
    METHOD_BANK = "BANK"
    METHOD_CHOICES = [(METHOD_MPESA, "Mpesa"), (METHOD_BANK, "Bank")]

    # State machine
    # ---------------------------------------------------------------------
    # REQUESTED  : funds reserved in KRIB; provider call not yet made (or
    #              made and we have no provider reference yet).
    # PROCESSING : provider acknowledged the transfer and returned a
    #              provider_reference. Funds remain reserved. Awaiting
    #              settlement confirmation via callback or polling.
    # PAID       : provider explicitly reported settlement. Final.
    # FAILED     : provider explicitly rejected before any settlement risk
    #              OR call failed before any provider reference. Funds are
    #              returned to available_balance.
    # REVERSED   : was PROCESSING but provider later confirmed the transfer
    #              did not settle (or our reconciliation determined this).
    #              Funds returned to available_balance.
    # PENDING    : legacy alias retained so older rows continue to render in
    #              the admin. New code paths never write PENDING.
    STATUS_REQUESTED = "REQUESTED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_PAID = "PAID"
    STATUS_FAILED = "FAILED"
    STATUS_REVERSED = "REVERSED"
    STATUS_PENDING = "PENDING"  # legacy
    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REVERSED, "Reversed"),
        (STATUS_PENDING, "Pending (legacy)"),
    ]

    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name="landlord_payouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    destination = models.CharField(max_length=255)
    bank_code = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts_requested",
    )
    marked_paid_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts_marked_paid",
    )
    marked_paid_at = models.DateTimeField(blank=True, null=True)
    # Client-supplied (or server-generated) idempotency key. Lets us safely
    # retry a payout without double-deducting if the original response was
    # lost in transit. Scoped per-landlord so two different landlords can
    # use the same UUID without collision (very unlikely, but unique-per-row
    # is the safest invariant).
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Provider's own transfer/tracking id. Stored so reconciliation can ask
    # the provider for the authoritative settlement status later.
    provider_reference = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    # Last raw provider status string (e.g. "SENT", "APPROVED", "FAILED").
    # Free-text because each provider uses different vocabulary.
    provider_status = models.CharField(max_length=50, blank=True, null=True)
    # Redacted/minimized last provider response. Run through
    # core.payments.redact.redact_payment_payload before persisting so
    # raw phone numbers / account numbers do not land in the DB.
    provider_response = models.JSONField(blank=True, null=True)
    processing_at = models.DateTimeField(blank=True, null=True)
    failed_at = models.DateTimeField(blank=True, null=True)
    reversed_at = models.DateTimeField(blank=True, null=True)
    last_reconciled_at = models.DateTimeField(blank=True, null=True)


class CustodyAuditLog(models.Model):
    """Append-only audit trail for admin-driven custody float operations.

    Phase 2A introduces an admin-driven cutover from the legacy KRIB-custody
    collection flow to direct landlord Paybill. These rows record who did what
    to which landlord: settlement payouts that drain the custody float, the
    actual collection_mode switch, and blocked switch attempts (so a landlord
    repeatedly hitting the safety rail is visible). Never mutated after insert.
    """

    ACTION_SETTLEMENT_PAYOUT = "settlement_payout"
    ACTION_CUTOVER = "cutover_to_direct_paybill"
    ACTION_CUTOVER_BLOCKED = "cutover_blocked"
    ACTION_CHOICES = [
        (ACTION_SETTLEMENT_PAYOUT, "Settlement payout"),
        (ACTION_CUTOVER, "Cutover to direct paybill"),
        (ACTION_CUTOVER_BLOCKED, "Cutover blocked"),
    ]

    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_audit_actions",
    )
    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name="custody_audit_logs")
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    # Balance snapshot at the moment the action was taken, so the audit row is
    # self-contained even after the live balance changes.
    available_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    locked_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    # Settlement payout amount (NULL for non-payout actions).
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payout = models.ForeignKey(
        LandlordPayout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_audit_logs",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} landlord={self.landlord_id} by actor={self.actor_id}"


class SubscriptionInvoice(models.Model):
    """Phase 2B: monthly KRIB platform-fee invoice for a landlord.

    Separate rail from rent collection. The amount is a snapshot of (billable
    units at run time) × per-unit price, frozen on generation. Once persisted,
    changing a lease's status does NOT retroactively alter the invoice —
    line items capture which units were billed for transparency.
    """

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FREE_TIER = "free_tier"
    STATUS_OVERDUE = "overdue"
    STATUS_WAIVED = "waived"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_FREE_TIER, "Free tier"),
        (STATUS_OVERDUE, "Overdue"),
        (STATUS_WAIVED, "Waived"),
    ]

    landlord = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscription_invoices",
    )
    # Period is the YYYY-MM string for the month the invoice covers.
    period = models.CharField(max_length=7)
    billable_units_count = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    generated_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    # Free-text reference to the IntaSend invoice / transaction the payment
    # arrived under. Not unique because a waiver leaves it blank.
    paid_via = models.CharField(max_length=120, blank=True, null=True)
    # IntaSend invoice_id we used when initiating the STK push for this
    # invoice. Mirrored here so the webhook can look the invoice back up by
    # reference without scanning every row.
    intasend_invoice_id = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        db_index=True,
    )
    # Local reference set before the STK provider call. It is intentionally
    # separate from intasend_invoice_id so concurrent pay attempts can be
    # blocked before IntaSend returns its invoice id.
    payment_reference = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        db_index=True,
    )
    payment_initiated_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period", "landlord_id"]
        constraints = [
            # PLAIN unique constraint — no `condition=`. Phase 1's W036 fix
            # explicitly taught us conditional unique constraints are silently
            # skipped on MySQL. Mirror that pattern: one invoice per landlord
            # per billing period at the database layer.
            models.UniqueConstraint(
                fields=["landlord", "period"],
                name="uniq_subscription_invoice_per_landlord_period",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gte=Decimal("0.00")),
                name="subscription_invoice_amount_non_negative",
            ),
        ]

    def __str__(self):
        return f"SubInvoice {self.landlord_id} {self.period} {self.status}"


class SubscriptionInvoiceLineItem(models.Model):
    """Snapshot of which units a SubscriptionInvoice was generated against.

    Lets the landlord see exactly the N units they were charged for. Stored
    even for free-tier invoices so a landlord browsing history can confirm
    "I was at 5 units last month, that's why it was free."
    """

    invoice = models.ForeignKey(
        SubscriptionInvoice,
        on_delete=models.CASCADE,
        related_name="line_items",
    )
    unit = models.ForeignKey(
        "Unit",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="subscription_line_items",
    )
    lease = models.ForeignKey(
        "Lease",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="subscription_line_items",
    )
    # Frozen human-readable labels in case the underlying unit/lease is later
    # deleted. Same approach as PaymentRecord.transaction_code: keep the
    # historical record self-contained.
    unit_label = models.CharField(max_length=255, blank=True)
    lease_status_at_snapshot = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["unit_label", "id"]

    def __str__(self):
        return f"{self.invoice_id} / {self.unit_label}"


class SubscriptionInvoiceAuditLog(models.Model):
    """Append-only audit trail for SubscriptionInvoice state changes.

    Distinct table from PaymentRecordAuditLog / CustodyAuditLog because the
    subscription rail has its own actions (generation, payment initiation,
    payment confirmation, manual waiver) and lives on the KRIB-platform
    surface, not the landlord-money surface.
    """

    ACTION_GENERATED = "generated"
    ACTION_PAYMENT_INITIATED = "payment_initiated"
    ACTION_PAYMENT_CONFIRMED = "payment_confirmed"
    ACTION_WAIVED = "waived"
    ACTION_STATUS_CHANGED = "status_changed"
    ACTION_CHOICES = [
        (ACTION_GENERATED, "Generated"),
        (ACTION_PAYMENT_INITIATED, "Payment initiated"),
        (ACTION_PAYMENT_CONFIRMED, "Payment confirmed"),
        (ACTION_WAIVED, "Waived"),
        (ACTION_STATUS_CHANGED, "Status changed"),
    ]

    invoice = models.ForeignKey(
        SubscriptionInvoice,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="subscription_audit_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.invoice_id}/{self.action}"


class MaintenanceRequest(models.Model):
    URGENCY_LOW = "low"
    URGENCY_MEDIUM = "medium"
    URGENCY_HIGH = "high"
    URGENCY_CHOICES = [
        (URGENCY_LOW, "Low"),
        (URGENCY_MEDIUM, "Medium"),
        (URGENCY_HIGH, "High"),
    ]

    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    tenant = models.ForeignKey(User, on_delete=models.CASCADE, related_name="maintenance_requests")
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, related_name="maintenance_requests")
    issue = models.TextField()
    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default=URGENCY_MEDIUM)
    photo_path = models.FileField(
        upload_to="maintenance/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png"])],
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Document(models.Model):
    TYPE_LEASE = "lease"
    TYPE_IDENTITY = "identity"
    TYPE_RECEIPT = "receipt"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_LEASE, "Lease"),
        (TYPE_IDENTITY, "ID / Passport"),
        (TYPE_RECEIPT, "Receipt"),
        (TYPE_OTHER, "Other"),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="documents")
    lease = models.ForeignKey(Lease, on_delete=models.SET_NULL, blank=True, null=True, related_name="documents")
    tenant = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="tenant_documents")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_OTHER)
    file_path = models.FileField(
        upload_to="documents/",
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
    )
    upload_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-upload_date"]

    def __str__(self):
        return f"{self.property.name} / {self.document_type}"


class Notification(models.Model):
    TYPE_GENERIC = "generic"
    TYPE_OVERDUE = "overdue"
    TYPE_CHOICES = [
        (TYPE_GENERIC, "Generic"),
        (TYPE_OVERDUE, "Overdue"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_GENERIC)
    lease = models.ForeignKey(Lease, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    period = models.CharField(max_length=7, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "type", "lease", "period"], name="uniq_overdue_notice_per_lease_period")
        ]


def _period_start(value):
    if not value:
        return None
    if hasattr(value, "year") and hasattr(value, "month"):
        return value.replace(day=1)
    try:
        return datetime.strptime(str(value), "%Y-%m").date().replace(day=1)
    except ValueError:
        return None


def _month_count_inclusive(start_month, end_month):
    if end_month < start_month:
        return 0
    return ((end_month.year - start_month.year) * 12) + (end_month.month - start_month.month) + 1


def _payment_period_start(payment):
    billing_period = getattr(payment, "billing_period", None)
    if billing_period:
        return billing_period.replace(day=1)
    period = getattr(payment, "period", None)
    if period:
        return _period_start(period)
    transaction_date = getattr(payment, "transaction_date", None)
    if transaction_date:
        return transaction_date.date().replace(day=1)
    created_at = getattr(payment, "created_at", None)
    if created_at:
        return created_at.date().replace(day=1)
    return None


def compute_lease_rent_status(lease, period=None, today=None):
    today = today or timezone.localdate()
    period = period or today.strftime("%Y-%m")
    target_month = _period_start(period) or today.replace(day=1)
    lease_start_month = lease.start_date.replace(day=1)
    lease_end_month = lease.end_date.replace(day=1) if lease.end_date else target_month
    effective_end_month = min(target_month, lease_end_month)

    billable_periods = _month_count_inclusive(lease_start_month, effective_end_month)
    if billable_periods <= 0:
        return {
            "period": period,
            "rent_due": Decimal("0.00"),
            "paid_sum": Decimal("0.00"),
            "balance": Decimal("0.00"),
            "status": "PAID",
            "current_period_paid_sum": Decimal("0.00"),
            "current_period_balance": Decimal("0.00"),
            "carried_forward_balance": Decimal("0.00"),
            "cumulative_rent_due": Decimal("0.00"),
            "cumulative_paid_sum": Decimal("0.00"),
        }

    current_period_paid_sum = Decimal("0.00")
    cumulative_paid_sum = Decimal("0.00")
    successful_payments = PaymentTransaction.objects.filter(
        lease=lease,
        status=PaymentTransaction.STATUS_SUCCESS,
    )
    confirmed_direct_payments = PaymentRecord.objects.filter(
        lease=lease,
        status=PaymentRecord.STATUS_CONFIRMED,
    )

    for payment in list(successful_payments) + list(confirmed_direct_payments):
        payment_month = _payment_period_start(payment)
        if not payment_month or payment_month > target_month:
            continue
        cumulative_paid_sum += payment.amount
        if payment_month == target_month:
            current_period_paid_sum += payment.amount

    rent_due = lease.rent_amount
    cumulative_rent_due = rent_due * billable_periods
    previous_periods_due = rent_due * max(billable_periods - 1, 0)
    paid_applied_to_previous = min(cumulative_paid_sum, previous_periods_due)
    carried_forward_balance = max(previous_periods_due - paid_applied_to_previous, Decimal("0.00"))
    remaining_paid_for_current = max(cumulative_paid_sum - previous_periods_due, Decimal("0.00"))
    current_period_balance = max(rent_due - min(remaining_paid_for_current, rent_due), Decimal("0.00"))
    balance = carried_forward_balance + current_period_balance

    if balance <= 0:
        status = "PAID"
    elif carried_forward_balance > 0:
        status = "OVERDUE"
    elif current_period_paid_sum > 0:
        status = "PARTIAL"
    else:
        status = "UNPAID"

    if current_period_balance > 0 and today.day > lease.due_day:
        status = "OVERDUE"

    if status == "OVERDUE" and balance > 0:
        Notification.objects.get_or_create(
            user=lease.tenant,
            type=Notification.TYPE_OVERDUE,
            lease=lease,
            period=period,
            defaults={
                "title": "Rent overdue",
                "message": f"Your outstanding rent balance of KES {balance} is overdue. Please clear it to avoid eviction procedures.",
            },
        )

    return {
        "period": period,
        "rent_due": rent_due,
        "paid_sum": current_period_paid_sum,
        "balance": balance,
        "status": status,
        "current_period_paid_sum": current_period_paid_sum,
        "current_period_balance": current_period_balance,
        "carried_forward_balance": carried_forward_balance,
        "cumulative_rent_due": cumulative_rent_due,
        "cumulative_paid_sum": cumulative_paid_sum,
    }


@receiver(post_save, sender=User)
def ensure_user_profiles(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if created:
        Profile.objects.get_or_create(user=instance)
        Tenant.objects.get_or_create(user=instance)
