from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0025_companyprofile_brand_dark_color_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="companyprofile",
            name="brand_button_text_color",
            field=models.CharField(
                blank=True,
                help_text="Hex color for apply button text e.g. #ffffff",
                max_length=7,
                null=True,
            ),
        ),
    ]
