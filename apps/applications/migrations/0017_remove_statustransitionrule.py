from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0016_alter_jobapplication_status_flexible"),
    ]

    operations = [
        migrations.DeleteModel(
            name="StatusTransitionRule",
        ),
    ]
