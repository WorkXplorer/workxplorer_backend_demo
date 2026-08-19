# Generated migrations for adding created_by_type to Resume

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("resumes", "0023_alter_resumelanguagecertificate_file_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="resume",
            name="created_by_type",
            field=models.CharField(
                choices=[
                    ("ai_generated", "AI Generated"),
                    ("candidate_created", "Candidate Created"),
                ],
                default="candidate_created",
                help_text="Whether the resume was created by AI or by the candidate",
                max_length=20,
            ),
        ),
    ]
