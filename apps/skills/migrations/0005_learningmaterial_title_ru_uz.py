from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("skills", "0004_learningmaterial_unique_learning_material_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="learningmaterial",
            name="title_ru",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="learningmaterial",
            name="title_uz",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]
