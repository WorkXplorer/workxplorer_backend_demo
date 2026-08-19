from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("hr_templates", "0007_migrate_status_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="template",
            name="status",
        ),
    ]
