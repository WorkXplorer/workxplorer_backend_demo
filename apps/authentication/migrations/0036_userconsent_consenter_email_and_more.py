from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0035_mobile_auth_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="userconsent",
            name="consenter_email",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Email (or name) of the consenter at the time of consent",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="userconsent",
            name="consenter_deleted",
            field=models.BooleanField(
                default=False,
                help_text="True when the consenting user or company no longer exists",
            ),
        ),
    ]
