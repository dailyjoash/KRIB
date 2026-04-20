from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_document_tenant_and_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="landlordpayout",
            name="bank_code",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
