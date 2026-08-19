from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banners", "0002_bannerslide_image_desktop_bannerslide_image_mobile_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="bannerslide",
            name="image_desktop_uz",
            field=models.ImageField(
                blank=True,
                help_text="Desktop background image for Uzbek locale. Falls back to image_desktop if not set.",
                null=True,
                upload_to="banner_slides/desktop/uz/",
            ),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="image_desktop_ru",
            field=models.ImageField(
                blank=True,
                help_text="Desktop background image for Russian locale. Falls back to image_desktop if not set.",
                null=True,
                upload_to="banner_slides/desktop/ru/",
            ),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="image_desktop_en",
            field=models.ImageField(
                blank=True,
                help_text="Desktop background image for English locale. Falls back to image_desktop if not set.",
                null=True,
                upload_to="banner_slides/desktop/en/",
            ),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="image_mobile_uz",
            field=models.ImageField(
                blank=True,
                help_text="Mobile background image for Uzbek locale. Falls back to image_mobile if not set.",
                null=True,
                upload_to="banner_slides/mobile/uz/",
            ),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="image_mobile_ru",
            field=models.ImageField(
                blank=True,
                help_text="Mobile background image for Russian locale. Falls back to image_mobile if not set.",
                null=True,
                upload_to="banner_slides/mobile/ru/",
            ),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="image_mobile_en",
            field=models.ImageField(
                blank=True,
                help_text="Mobile background image for English locale. Falls back to image_mobile if not set.",
                null=True,
                upload_to="banner_slides/mobile/en/",
            ),
        ),
    ]
