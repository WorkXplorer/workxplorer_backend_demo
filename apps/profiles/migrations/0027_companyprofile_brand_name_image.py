from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0026_companyprofile_brand_button_text_color"),
    ]

    operations = [
        migrations.RenameField(
            model_name="companyprofile",
            old_name="brand_branding_image",
            new_name="brand_name_image",
        ),
        migrations.AlterField(
            model_name="companyprofile",
            name="brand_name_image",
            field=models.ImageField(
                blank=True,
                help_text="Image of the company wordmark/name to show instead of plain text in the banner.",
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
