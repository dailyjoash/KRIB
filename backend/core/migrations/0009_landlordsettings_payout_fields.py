from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_landlordpayout_bank_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="landlordsettings",
            name="payout_bank_code",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="landlordsettings",
            name="payout_destination",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="landlordsettings",
            name="payout_method",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
