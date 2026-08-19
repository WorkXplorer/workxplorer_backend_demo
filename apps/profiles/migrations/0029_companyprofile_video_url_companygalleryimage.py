from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0028_companyprofile_brand_page_type_and_stats"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="video_url",
            field=models.URLField(
                blank=True,
                help_text="URL to a company video (YouTube, Vimeo, or direct link).",
                max_length=500,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="CompanyGalleryImage",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "id",
                    utils.fields.UUIDField(
                        editable=False, primary_key=True, serialize=False, version=7
                    ),
                ),
                (
                    "image",
                    models.ImageField(
                        help_text="Gallery image for the branded company page.",
                        upload_to="company_gallery/",
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=["jpg", "jpeg", "png", "webp"]
                            )
                        ],
                    ),
                ),
                (
                    "order",
                    models.PositiveIntegerField(
                        default=0, help_text="Display order (lower = first)."
                    ),
                ),
                (
                    "company_profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gallery_images",
                        to="profiles.companyprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "Company Gallery Image",
                "verbose_name_plural": "Company Gallery Images",
                "ordering": ["order"],
            },
        ),
    ]
