# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0010_alter_jobapplication_status"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="jobapplication",
            name="expected_salary",
        ),
        migrations.RemoveField(
            model_name="jobapplication",
            name="salary_currency",
        ),
    ]
