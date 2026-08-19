from django.db import migrations, models


def add_ai_failed_category(apps, schema_editor):
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')
    ApplicationStatusModel = apps.get_model('applications', 'ApplicationStatusModel')

    ai_failed_category, created = StatusCategory.objects.get_or_create(
        key='AI_FAILED',
        defaults={
            'label': 'AI Rejected',
            'description': 'Application auto-rejected by AI evaluation.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'is_single_column': True,
            'position': 12,
        },
    )

    ai_failed_status_def = {
        'key': 'AI_FAILED',
        'label': 'AI Rejected',
        'category': 'AI_FAILED',
        'color': '#F97316',
        'position': 9,
        'show_in_kanban': False,
        'translations': {
            'ru': 'Отклонено AI',
            'uz': 'AI rad etdi',
        },
    }

    default_template = StatusTemplate.objects.filter(is_default=True).first()
    if default_template:
        statuses = list(default_template.statuses)
        has_ai_failed = any(s.get('key') == 'AI_FAILED' for s in statuses)
        if not has_ai_failed:
            statuses.append(ai_failed_status_def)
            default_template.statuses = statuses
            default_template.save(update_fields=['statuses'])

    Company = apps.get_model('authentication', 'Company')
    for company in Company.objects.iterator():
        exists = ApplicationStatusModel.objects.filter(
            company=company,
            key='AI_FAILED',
        ).exists()
        if not exists:
            ApplicationStatusModel.objects.create(
                key='AI_FAILED',
                label='AI Rejected',
                company=company,
                category=ai_failed_category,
                color='#F97316',
                position=9,
                show_in_kanban=False,
                is_default=True,
                translations={'ru': 'Отклонено AI', 'uz': 'AI rad etdi'},
            )


def reverse_ai_failed_category(apps, schema_editor):
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')
    ApplicationStatusModel = apps.get_model('applications', 'ApplicationStatusModel')

    ApplicationStatusModel.objects.filter(
        key='AI_FAILED', is_default=True,
    ).delete()

    default_template = StatusTemplate.objects.filter(is_default=True).first()
    if default_template:
        statuses = [s for s in default_template.statuses if s.get('key') != 'AI_FAILED']
        default_template.statuses = statuses
        default_template.save(update_fields=['statuses'])

    StatusCategory.objects.filter(key='AI_FAILED').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0024_remove_applicationdocument_uploaded_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='statuscategory',
            name='key',
            field=models.CharField(
                choices=[
                    ('APPLIED', 'Applied'),
                    ('SCREENING', 'Screening'),
                    ('INTERVIEWING', 'Interviewing'),
                    ('ASSESSMENT', 'Assessment'),
                    ('TRAINING', 'Training'),
                    ('OFFERED', 'Offered'),
                    ('HIRED', 'Hired'),
                    ('OFFER_REJECTED', 'Offer Rejected'),
                    ('REJECTED', 'Rejected'),
                    ('WITHDRAWN', 'Withdrawn'),
                    ('ON_HOLD', 'On Hold'),
                    ('AI_FAILED', 'AI Rejected'),
                ],
                help_text="Unique identifier for the category (e.g., 'HIRED', 'REJECTED')",
                max_length=50,
                unique=True,
            ),
        ),
        migrations.RunPython(
            add_ai_failed_category,
            reverse_code=reverse_ai_failed_category,
        ),
    ]
