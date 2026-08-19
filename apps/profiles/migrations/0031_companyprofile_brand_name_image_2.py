from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0030_companyprofile_video_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="brand_name_image_2",
            field=models.ImageField(
                blank=True,
                help_text="Second brand name image (e.g. full logo with transparent background) for custom branded pages.",
                null=True,
                upload_to="company_name_images/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["jpg", "jpeg", "png", "webp"]
                    )
                ],
            ),
        ),
    ]
