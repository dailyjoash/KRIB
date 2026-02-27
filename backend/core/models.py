import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


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

    def __str__(self):
        return f"{self.user.username} ({self.role})"


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
    due_day = models.PositiveSmallIntegerField(default=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)

    def clean(self):
        if self.status == self.STATUS_ACTIVE:
            existing = Lease.objects.filter(unit=self.unit, status=self.STATUS_ACTIVE)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError("Only one active lease is allowed per unit.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.rent_amount:
            self.rent_amount = self.unit.rent_amount
        super().save(*args, **kwargs)
        self.unit.status = Unit.STATUS_OCCUPIED if self.status == self.STATUS_ACTIVE else Unit.STATUS_VACANT
        self.unit.save(update_fields=["status"])

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
    period = models.CharField(max_length=7)  # YYYY-MM
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    merchant_request_id = models.CharField(max_length=100, blank=True, null=True)
    checkout_request_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    mpesa_receipt = models.CharField(max_length=100, blank=True, null=True)
    result_code = models.IntegerField(blank=True, null=True)
    result_desc = models.CharField(max_length=255, blank=True, null=True)
    transaction_date = models.DateTimeField(blank=True, null=True)
    raw_callback = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.tenant.username} {self.period} {self.amount}"


class MaintenanceRequest(models.Model):
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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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


def compute_lease_rent_status(lease, period=None, today=None):
    today = today or timezone.localdate()
    period = period or today.strftime("%Y-%m")
    paid_sum = (
        PaymentTransaction.objects.filter(
            lease=lease,
            period=period,
            status=PaymentTransaction.STATUS_SUCCESS,
        ).aggregate(total=Coalesce(Sum("amount"), Decimal("0.00")))["total"]
    )
    rent_due = lease.rent_amount
    balance = rent_due - paid_sum

    if balance <= 0:
        status = "PAID"
    elif paid_sum > 0:
        status = "PARTIAL"
    else:
        status = "UNPAID"

    if today.day > lease.due_day and balance > 0:
        status = "OVERDUE"
        Notification.objects.get_or_create(
            user=lease.tenant,
            type=Notification.TYPE_OVERDUE,
            lease=lease,
            period=period,
            defaults={
                "title": "Rent overdue",
                "message": f"Your rent for {today.strftime('%B %Y')} is overdue. Please clear your balance to avoid eviction procedures.",
            },
        )

    return {
        "period": period,
        "rent_due": rent_due,
        "paid_sum": paid_sum,
        "balance": balance,
        "status": status,
    }


@receiver(post_save, sender=User)
def ensure_user_profiles(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
        Tenant.objects.get_or_create(user=instance)
