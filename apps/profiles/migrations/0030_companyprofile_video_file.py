from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0029_companyprofile_video_url_companygalleryimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="video_file",
            field=models.FileField(
                blank=True,
                help_text="Uploaded company video file (mp4, webm, mov, m4v).",
                null=True,
                upload_to="company_videos/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["mp4", "webm", "mov", "m4v"]
                    )
                ],
            ),
        ),
    ]
