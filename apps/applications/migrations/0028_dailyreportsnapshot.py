from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0027_jobapplication_is_demo"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailyReportSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created at")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated at")),
                (
                    "report_date",
                    models.DateField(
                        help_text="The local day this report describes.", unique=True
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        help_text=(
                            "The full report payload as built for the bot. Stored "
                            "verbatim so a later reader sees what was actually "
                            "reported, not what today's code would compute."
                        )
                    ),
                ),
            ],
            options={
                "verbose_name": "Daily report snapshot",
                "verbose_name_plural": "Daily report snapshots",
                "ordering": ["-report_date"],
            },
        ),
    ]
