from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0024_companyprofile_brand_accent_color_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="brand_dark_color",
            field=models.CharField(
                blank=True,
                help_text="Hex color for title and salary text e.g. #0D1411",
                max_length=7,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="brand_font_file",
            field=models.FileField(
                blank=True,
                help_text="Upload a custom font file (woff, woff2, ttf, otf). Overrides brand_font if set.",
                null=True,
                upload_to="company_fonts/",
                validators=[FileExtensionValidator(allowed_extensions=["woff", "woff2", "ttf", "otf"])],
            ),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="brand_branding_image",
            field=models.ImageField(
                blank=True,
                help_text="Pre-designed branding image to replace the logo/name/tagline column in the banner.",
                null=True,
                upload_to="company_branding/",
                validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
            ),
        ),
    ]
