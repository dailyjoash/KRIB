import uuid

from django.db import migrations, models


def _backfill_idempotency_keys(apps, schema_editor):
    """Ensure every legacy row has a unique idempotency_key.

    Django's AddField with a callable default *does* call the default per
    row in modern versions, but we re-run it explicitly here so the
    follow-up AlterField that sets unique=True cannot fail on a duplicate
    or null value if the table was migrated on a slightly older Django.
    """
    LandlordPayout = apps.get_model("core", "LandlordPayout")
    for row in LandlordPayout.objects.filter(idempotency_key__isnull=True):
        row.idempotency_key = uuid.uuid4()
        row.save(update_fields=["idempotency_key"])


def _no_op_reverse(apps, schema_editor):
    # The reverse direction would drop UUIDs we generated, which is fine —
    # nothing depends on the specific values.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_integrity_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="landlordpayout",
            name="idempotency_key",
            # Start nullable so existing rows survive the schema step; the
            # data migration + AlterField below tighten this to UNIQUE NOT NULL.
            field=models.UUIDField(default=uuid.uuid4, null=True, editable=False),
        ),
        migrations.RunPython(_backfill_idempotency_keys, _no_op_reverse),
        migrations.AlterField(
            model_name="landlordpayout",
            name="idempotency_key",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="provider_reference",
            field=models.CharField(blank=True, db_index=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="provider_status",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="provider_response",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="processing_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="failed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="landlordpayout",
            name="last_reconciled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="landlordpayout",
            name="status",
            field=models.CharField(
                choices=[
                    ("REQUESTED", "Requested"),
                    ("PROCESSING", "Processing"),
                    ("PAID", "Paid"),
                    ("FAILED", "Failed"),
                    ("REVERSED", "Reversed"),
                    ("PENDING", "Pending (legacy)"),
                ],
                default="REQUESTED",
                max_length=20,
            ),
        ),
    ]
