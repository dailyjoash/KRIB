from django.db import migrations, models
from django.db.models import F


def backfill_blank_payment_reference_to_null(apps, schema_editor):
    """Empty-string references become the NULL sentinel."""
    Lease = apps.get_model("core", "Lease")
    Lease.objects.filter(payment_reference="").update(payment_reference=None)


def backfill_active_unit_key(apps, schema_editor):
    """Mirror unit_id onto active leases; inactive leases keep NULL."""
    Lease = apps.get_model("core", "Lease")
    Lease.objects.filter(status="active").update(active_unit_key=F("unit_id"))
    Lease.objects.exclude(status="active").update(active_unit_key=None)


def _drop_partial_index_if_present(index_name):
    """Drop a conditional unique index only on backends that created it.

    The two original conditional UniqueConstraints were materialized as partial
    unique indexes on backends that support them (SQLite in the test suite,
    Postgres) but were silently skipped on MySQL (system check W036 - MySQL has
    no partial index support). A naive RemoveConstraint therefore errors on
    MySQL ("check that column/key exists"), so we only issue the DROP where the
    index can actually exist.
    """

    def _inner(apps, schema_editor):
        if schema_editor.connection.vendor == "mysql":
            return
        schema_editor.execute(
            "DROP INDEX IF EXISTS %s" % schema_editor.quote_name(index_name)
        )

    return _inner


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_direct_paybill_phase1"),
    ]

    operations = [
        # --- Fix 1: payment_reference NULL sentinel -------------------------
        # Make the column nullable and convert existing "" to NULL BEFORE the
        # new plain unique constraint is added.
        migrations.AlterField(
            model_name="lease",
            name="payment_reference",
            field=models.CharField(blank=True, db_index=True, max_length=8, null=True),
        ),
        migrations.RunPython(
            backfill_blank_payment_reference_to_null,
            migrations.RunPython.noop,
        ),
        # Swap the conditional unique (skipped on MySQL) for a plain one. The
        # state removal keeps Django's model state in sync on every backend;
        # the database removal is a real DROP only where the index exists.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="lease",
                    name="lease_unique_payment_reference_per_landlord",
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _drop_partial_index_if_present(
                        "lease_unique_payment_reference_per_landlord"
                    ),
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.UniqueConstraint(
                fields=["payment_reference_landlord", "payment_reference"],
                name="lease_unique_payment_reference_per_landlord",
            ),
        ),
        # --- Fix 2: one active lease per unit via maintained key column -----
        migrations.AddField(
            model_name="lease",
            name="active_unit_key",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(
            backfill_active_unit_key,
            migrations.RunPython.noop,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="lease",
                    name="lease_one_active_per_unit",
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _drop_partial_index_if_present("lease_one_active_per_unit"),
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.UniqueConstraint(
                fields=["active_unit_key"],
                name="lease_one_active_per_unit",
            ),
        ),
    ]
