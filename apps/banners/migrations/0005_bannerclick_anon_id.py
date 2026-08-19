from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banners", "0004_bannerclick"),
    ]

    operations = [
        migrations.AddField(
            model_name="bannerclick",
            name="anon_id",
            field=models.CharField(blank=True, default="", help_text="Browser-generated UUID for anonymous user identification", max_length=36),
        ),
    ]
