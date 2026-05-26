from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_payout_destination_cooldown"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="profile",
            constraint=models.CheckConstraint(
                condition=models.Q(wallet_available__gte=Decimal("0.00")),
                name="profile_wallet_available_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="profile",
            constraint=models.CheckConstraint(
                condition=models.Q(wallet_locked__gte=Decimal("0.00")),
                name="profile_wallet_locked_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.CheckConstraint(
                condition=models.Q(rent_amount__gte=Decimal("0.00")),
                name="unit_rent_amount_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="unit",
            constraint=models.CheckConstraint(
                condition=models.Q(deposit__gte=Decimal("0.00")),
                name="unit_deposit_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.CheckConstraint(
                condition=models.Q(rent_amount__gte=Decimal("0.00")),
                name="lease_rent_amount_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.CheckConstraint(
                condition=models.Q(due_day__gte=1) & models.Q(due_day__lte=28),
                name="lease_due_day_in_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="lease",
            constraint=models.UniqueConstraint(
                fields=["unit"],
                condition=models.Q(status="active"),
                name="lease_one_active_per_unit",
            ),
        ),
        migrations.AddConstraint(
            model_name="paymenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="paymenttransaction_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="landlordbalance",
            constraint=models.CheckConstraint(
                condition=models.Q(available_balance__gte=Decimal("0.00")),
                name="landlordbalance_available_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="landlordbalance",
            constraint=models.CheckConstraint(
                condition=models.Q(locked_balance__gte=Decimal("0.00")),
                name="landlordbalance_locked_non_negative",
            ),
        ),
    ]
