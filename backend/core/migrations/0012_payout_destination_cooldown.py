from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_payout_audit_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="landlordsettings",
            name="payout_destination_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
