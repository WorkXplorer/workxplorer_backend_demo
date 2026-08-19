from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("banners", "0003_bannerslide_locale_images"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BannerClick",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slide_type", models.CharField(max_length=20)),
                ("vacancy_id", models.UUIDField(blank=True, null=True)),
                ("cta_url", models.CharField(blank=True, default="", max_length=500)),
                ("clicked_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="banner_clicks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Banner Click",
                "verbose_name_plural": "Banner Clicks",
                "ordering": ["-clicked_at"],
            },
        ),
    ]
