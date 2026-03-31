from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_landlordsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="maintenancerequest",
            name="urgency",
            field=models.CharField(
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
                default="medium",
                max_length=20,
            ),
        ),
    ]
