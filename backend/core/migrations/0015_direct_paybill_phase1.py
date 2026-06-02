import random
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _random_reference(length=5):
    return "".join(random.choice(_REFERENCE_ALPHABET) for _ in range(length))


def _candidate_from_unit(unit_number):
    cleaned = "".join(ch for ch in (unit_number or "").upper() if ch.isalnum())
    if 4 <= len(cleaned) <= 6:
        return cleaned
    if len(cleaned) > 6:
        return cleaned[:6]
    if cleaned:
        return f"{cleaned}{_random_reference(max(4 - len(cleaned), 1))}"
    return ""


def _reference_exists(Lease, landlord_id, reference, exclude_pk=None):
    qs = Lease.objects.filter(payment_reference_landlord_id=landlord_id, payment_reference=reference)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def backfill_lease_payment_references(apps, schema_editor):
    Lease = apps.get_model("core", "Lease")
    leases = Lease.objects.select_related("unit", "unit__property").filter(payment_reference="")
    for lease in leases:
        landlord_id = lease.unit.property.landlord_id
        candidate = _candidate_from_unit(lease.unit.unit_number)
        if not candidate or _reference_exists(Lease, landlord_id, candidate, lease.pk):
            for _ in range(100):
                candidate = _random_reference(5)
                if not _reference_exists(Lease, landlord_id, candidate, lease.pk):
                    break
            else:
                raise RuntimeError(f"Could not allocate payment reference for lease {lease.pk}")
        lease.payment_reference_landlord_id = landlord_id
        lease.payment_reference = candidate
        lease.save(update_fields=["payment_reference_landlord", "payment_reference"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_payout_lifecycle"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="landlordsettings",
            name="collection_mode",
            field=models.CharField(
                choices=[
                    ("custody_legacy", "KRIB custody legacy"),
                    ("direct_paybill", "Direct landlord Paybill"),
                ],
                default="custody_legacy",
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="LandlordCollectionAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "collection_method",
                    models.CharField(choices=[("mpesa_paybill", "M-Pesa Paybill")], default="mpesa_paybill", max_length=30),
                ),
                ("paybill_number", models.CharField(max_length=20)),
                ("registered_business_name", models.CharField(max_length=200)),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("unverified", "Unverified"),
                            ("pending", "Pending"),
                            ("verified", "Verified"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("verification_notes", models.TextField(blank=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("callback_status", models.CharField(blank=True, max_length=50, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "landlord",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collection_account",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "verified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="verified_collection_accounts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("paybill_number",), name="uniq_landlord_collection_paybill"),
                ],
            },
        ),
        migrations.AddField(
            model_name="lease",
            name="payment_reference",
            field=models.CharField(blank=True, db_index=True, max_length=8),
        ),
        migrations.AddField(
            model_name="lease",
            name="payment_reference_landlord",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_lease_payment_references, noop_reverse),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.UniqueConstraint(
                fields=("payment_reference_landlord", "payment_reference"),
                condition=~models.Q(payment_reference=""),
                name="lease_unique_payment_reference_per_landlord",
            ),
        ),
        migrations.CreateModel(
            name="PaymentRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "source",
                    models.CharField(choices=[("direct_paybill", "Direct landlord Paybill")], default="direct_paybill", max_length=30),
                ),
                ("period", models.CharField(max_length=7)),
                ("phone_number", models.CharField(max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("allocated_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("transaction_code", models.CharField(max_length=100, unique=True)),
                ("transaction_date", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_confirmation", "Pending confirmation"),
                            ("confirmed", "Confirmed"),
                            ("rejected", "Rejected"),
                            ("unmatched", "Unmatched"),
                            ("disputed", "Disputed"),
                        ],
                        default="pending_confirmation",
                        max_length=30,
                    ),
                ),
                ("confirmation_note", models.TextField(blank=True)),
                ("rejection_note", models.TextField(blank=True)),
                ("flagged_reason", models.CharField(blank=True, max_length=255)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "collection_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payment_records",
                        to="core.landlordcollectionaccount",
                    ),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="confirmed_direct_payment_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "landlord",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="landlord_direct_payment_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "lease",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="direct_payment_records",
                        to="core.lease",
                    ),
                ),
                (
                    "rejected_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rejected_direct_payment_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="submitted_direct_payment_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="direct_payment_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(amount__gt=Decimal("0.00")), name="paymentrecord_amount_positive"),
                    models.CheckConstraint(condition=models.Q(allocated_amount__gte=Decimal("0.00")), name="paymentrecord_allocated_non_negative"),
                    models.CheckConstraint(condition=models.Q(allocated_amount__lte=models.F("amount")), name="paymentrecord_allocated_lte_amount"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PaymentRecordAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("submit", "Submit"),
                            ("confirm", "Confirm"),
                            ("reject", "Reject"),
                            ("attach", "Attach"),
                        ],
                        max_length=20,
                    ),
                ),
                ("old_status", models.CharField(blank=True, max_length=30)),
                ("new_status", models.CharField(blank=True, max_length=30)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="direct_payment_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "payment_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="core.paymentrecord",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
    ]
