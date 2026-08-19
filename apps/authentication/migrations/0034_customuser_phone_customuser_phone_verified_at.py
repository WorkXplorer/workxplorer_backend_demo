from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0033_customuser_preferred_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="phone",
            field=models.CharField(
                max_length=20,
                null=True,
                blank=True,
                unique=True,
                help_text="Verified phone number in +998XXXXXXXXX format. Usable as an alternate login identifier once verified.",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="phone_verified_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="When the phone number was confirmed via OTP. Null means unverified.",
            ),
        ),
    ]
