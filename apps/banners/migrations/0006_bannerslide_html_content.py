from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banners", "0005_bannerclick_anon_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="bannerslide",
            name="html_content",
            field=models.TextField(blank=True, default="", help_text="Full HTML for this banner slide. Rendered in a sandboxed iframe. Leave blank to use image/structured layout."),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="html_content_uz",
            field=models.TextField(blank=True, default="", help_text="HTML for Uzbek locale. Falls back to html_content."),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="html_content_ru",
            field=models.TextField(blank=True, default="", help_text="HTML for Russian locale. Falls back to html_content."),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="html_content_en",
            field=models.TextField(blank=True, default="", help_text="HTML for English locale. Falls back to html_content."),
        ),
    ]
