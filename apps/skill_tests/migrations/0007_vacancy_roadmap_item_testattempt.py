from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("student_analytics", "0005_vacancy_roadmap"),
        ("skill_tests", "0006_skilltest_candidate"),
    ]

    operations = [
        migrations.AddField(
            model_name="testattempt",
            name="vacancy_roadmap_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="test_attempts",
                to="student_analytics.vacancyroadmapitem",
            ),
        ),
    ]
