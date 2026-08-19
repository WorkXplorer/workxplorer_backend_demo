from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0027_companyprofile_brand_name_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="brand_page_type",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=50,
                help_text="Slug for custom pages, e.g. 'safia'. Drives dynamic component import on frontend.",
            ),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="employees_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="locations_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="founded_year",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="rating",
            field=models.DecimalField(blank=True, null=True, max_digits=3, decimal_places=1),
        ),
        migrations.AddField(
            model_name="companyprofile",
            name="reviews_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
