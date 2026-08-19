# Generated migration: add ApplicationAIEvaluation model

from django.db import migrations, models
import django.db.models.deletion
import utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0019_add_status_categories_and_column_type'),
    ]

    operations = [
        # Add RESUME choice to ApplicationDocumentTypes (no schema change needed
        # as document_type is a CharField — choices are enforced at app level only)

        # Create ApplicationAIEvaluation model
        migrations.CreateModel(
            name='ApplicationAIEvaluation',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', utils.fields.UUIDField(editable=False, primary_key=True, serialize=False, version=7)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('processing', 'Processing'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=20,
                )),
                ('overall_score', models.FloatField(
                    blank=True,
                    help_text='0-100 match score from AI evaluation',
                    null=True,
                )),
                ('result', models.JSONField(
                    blank=True,
                    help_text='Full AI evaluation JSON result',
                    null=True,
                )),
                ('job_queue_id', models.UUIDField(
                    blank=True,
                    help_text='Reference to the JobQueue entry tracking this evaluation task',
                    null=True,
                )),
                ('error_message', models.TextField(
                    blank=True,
                    help_text='Error details if evaluation failed',
                    null=True,
                )),
                ('evaluated_at', models.DateTimeField(
                    blank=True,
                    help_text='Timestamp when evaluation was completed',
                    null=True,
                )),
                ('application', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ai_evaluation',
                    to='applications.jobapplication',
                )),
            ],
            options={
                'verbose_name': 'Application AI Evaluation',
                'verbose_name_plural': 'Application AI Evaluations',
            },
        ),
        migrations.AddIndex(
            model_name='applicationaievaluation',
            index=models.Index(fields=['status'], name='application_status_idx'),
        ),
        migrations.AddIndex(
            model_name='applicationaievaluation',
            index=models.Index(fields=['overall_score'], name='application_score_idx'),
        ),
    ]
