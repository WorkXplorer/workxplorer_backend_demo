from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("banners", "0006_bannerslide_html_content"),
    ]

    operations = [
        migrations.RemoveField(model_name="bannerslide", name="html_content"),
        migrations.RemoveField(model_name="bannerslide", name="html_content_uz"),
        migrations.RemoveField(model_name="bannerslide", name="html_content_ru"),
        migrations.RemoveField(model_name="bannerslide", name="html_content_en"),
        migrations.AddField(
            model_name="bannerslide",
            name="html_file",
            field=models.FileField(
                blank=True, null=True,
                upload_to="banner_slides/html/",
                help_text="Upload an .html file. Rendered in a sandboxed iframe. Leave blank to use image/structured layout.",
            ),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="html_file_uz",
            field=models.FileField(blank=True, null=True, upload_to="banner_slides/html/uz/", help_text="HTML file for Uzbek locale. Falls back to html_file."),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="html_file_ru",
            field=models.FileField(blank=True, null=True, upload_to="banner_slides/html/ru/", help_text="HTML file for Russian locale. Falls back to html_file."),
        ),
        migrations.AddField(
            model_name="bannerslide",
            name="html_file_en",
            field=models.FileField(blank=True, null=True, upload_to="banner_slides/html/en/", help_text="HTML file for English locale. Falls back to html_file."),
        ),
    ]
