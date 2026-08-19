# Generated migration: add new status categories and column-type support

from django.db import migrations, models


def add_new_categories_and_flags(apps, schema_editor):
    """
    Affected StatusCategories — all 11 rows:
    =========================================
    INSERT (new):
      - ASSESSMENT          (key='ASSESSMENT',          is_single_column=False, is_terminal=False)
      - TRAINING            (key='TRAINING',            is_single_column=False, is_terminal=False)
      - OFFER_REJECTED      (key='OFFER_REJECTED',      is_single_column=True,  is_terminal=True)

    UPDATE (existing, is_single_column set):
      - APPLIED             → is_single_column=True
      - SCREENING           → is_single_column=False
      - INTERVIEWING        → is_single_column=False
      - OFFERED             → is_single_column=True
      - HIRED               → is_single_column=True
      - REJECTED            → is_single_column=True
      - WITHDRAWN           → is_single_column=True
      - ON_HOLD             → is_single_column=False

    UPDATE (existing, is_terminal changed):
      - OFFER_REJECTED      → is_terminal=True (already set on creation above)

    UPDATE (position renumbered):
      - ASSESSMENT          → position=4
      - TRAINING            → position=5
      - OFFERED             → position=6 (was 4)
      - HIRED               → position=7 (was 5)
      - OFFER_REJECTED      → position=8
      - REJECTED            → position=9 (was 6)
      - WITHDRAWN           → position=10 (was 7)
      - ON_HOLD             → position=11 (was 8)

    Affected ApplicationStatusModel rows:
    ======================================
    UPDATE (WITHDRAWN category, per-company):
      - show_in_kanban → False (where currently True)
      This ensures WITHDRAWN-category statuses are hidden from all kanban boards.

    Affected StatusTemplate rows:
    =============================
    UPDATE (default template):
      - OFFER_REJECTED status: category changed from 'REJECTED' to 'OFFER_REJECTED'
      - New statuses added: ASSESSMENT (cat=ASSESSMENT), TRAINING (cat=TRAINING)
    """
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    ApplicationStatusModel = apps.get_model('applications', 'ApplicationStatusModel')
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')

    # ----- 1. Insert new categories -----
    new_categories = [
        {
            'key': 'ASSESSMENT',
            'label': 'Assessment',
            'description': 'Test tasks, scoring and evaluation.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'is_single_column': False,
            'position': 4,
        },
        {
            'key': 'TRAINING',
            'label': 'Training',
            'description': 'Onboarding, probation period.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'is_single_column': False,
            'position': 5,
        },
        {
            'key': 'OFFER_REJECTED',
            'label': 'Offer Rejected',
            'description': 'Candidate declined the offer. Terminal negative state.',
            'is_terminal': True,
            'is_positive_outcome': False,
            'is_single_column': True,
            'position': 8,
        },
    ]
    for data in new_categories:
        StatusCategory.objects.get_or_create(key=data['key'], defaults=data)

    # ----- 2. Set is_single_column flags on existing categories -----
    single_column_keys = {'APPLIED', 'OFFERED', 'HIRED', 'REJECTED', 'WITHDRAWN', 'OFFER_REJECTED'}
    StatusCategory.objects.filter(key__in=single_column_keys).update(is_single_column=True)
    # multi-column categories already default to False, but be explicit:
    multi_column_keys = {'SCREENING', 'INTERVIEWING', 'ASSESSMENT', 'TRAINING', 'ON_HOLD'}
    StatusCategory.objects.filter(key__in=multi_column_keys).update(is_single_column=False)

    # ----- 3. Re-number positions to match the spec flow -----
    position_map = {
        'APPLIED': 1,
        'SCREENING': 2,
        'INTERVIEWING': 3,
        'ASSESSMENT': 4,
        'TRAINING': 5,
        'OFFERED': 6,
        'HIRED': 7,
        'OFFER_REJECTED': 8,
        'REJECTED': 9,
        'WITHDRAWN': 10,
        'ON_HOLD': 11,
    }
    for key, pos in position_map.items():
        StatusCategory.objects.filter(key=key).update(position=pos)

    # ----- 4. Hide WITHDRAWN from kanban -----
    withdrawn_category = StatusCategory.objects.filter(key='WITHDRAWN').first()
    if withdrawn_category:
        ApplicationStatusModel.objects.filter(
            category=withdrawn_category,
            show_in_kanban=True,
        ).update(show_in_kanban=False)

    # ----- 5. Update default template -----
    default_template = StatusTemplate.objects.filter(is_default=True).first()
    if default_template:
        statuses = list(default_template.statuses)

        # 5a. Fix OFFER_REJECTED category: was 'REJECTED', now 'OFFER_REJECTED'
        offer_rejected_found = False
        for s in statuses:
            if s.get('key') == 'OFFER_REJECTED':
                s['category'] = 'OFFER_REJECTED'
                offer_rejected_found = True
                break

        # 5b. Add ASSESSMENT and TRAINING statuses (after INTERVIEWED, before OFFERED)
        if not offer_rejected_found:
            # OFFER_REJECTED not in template — add it with the new category
            statuses.append({
                'key': 'OFFER_REJECTED',
                'label': 'Offer Rejected',
                'category': 'OFFER_REJECTED',
                'color': '#EF4444',
                'position': 8,
                'show_in_kanban': True,
                'translations': {
                    'ru': 'Предложение отклонено',
                    'uz': 'Taklif rad etildi',
                },
            })

        assessment_status = {
            'key': 'ASSESSMENT',
            'label': 'Assessment',
            'category': 'ASSESSMENT',
            'color': '#EC4899',
            'position': 4,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Оценка',
                'uz': 'Baholash',
            },
        }
        training_status = {
            'key': 'TRAINING',
            'label': 'Training',
            'category': 'TRAINING',
            'color': '#14B8A6',
            'position': 5,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Обучение',
                'uz': "O'qitish",
            },
        }

        has_assessment = any(s.get('key') == 'ASSESSMENT' for s in statuses)
        has_training = any(s.get('key') == 'TRAINING' for s in statuses)

        if not has_assessment:
            statuses.append(assessment_status)
        if not has_training:
            statuses.append(training_status)

        default_template.statuses = statuses
        default_template.save(update_fields=['statuses'])


def reverse_new_categories_and_flags(apps, schema_editor):
    """Rollback: delete new categories and reset flags."""
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    ApplicationStatusModel = apps.get_model('applications', 'ApplicationStatusModel')
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')

    # Delete new categories
    StatusCategory.objects.filter(key__in=['ASSESSMENT', 'TRAINING', 'OFFER_REJECTED']).delete()

    # Reset is_single_column to False on all categories
    StatusCategory.objects.all().update(is_single_column=False)

    # Reset positions to original
    original_positions = {
        'APPLIED': 1,
        'SCREENING': 2,
        'INTERVIEWING': 3,
        'OFFERED': 4,
        'HIRED': 5,
        'REJECTED': 6,
        'WITHDRAWN': 7,
        'ON_HOLD': 8,
    }
    for key, pos in original_positions.items():
        StatusCategory.objects.filter(key=key).update(position=pos)

    # Restore WITHDRAWN kanban visibility (was originally True for some)
    withdrawn_category = StatusCategory.objects.filter(key='WITHDRAWN').first()
    if withdrawn_category:
        ApplicationStatusModel.objects.filter(category=withdrawn_category).update(show_in_kanban=True)

    # Restore default template OFFER_REJECTED category
    default_template = StatusTemplate.objects.filter(is_default=True).first()
    if default_template:
        statuses = list(default_template.statuses)
        for s in statuses:
            if s.get('key') == 'OFFER_REJECTED':
                s['category'] = 'REJECTED'
                break
        # Remove ASSESSMENT/TRAINING if they were added
        statuses = [s for s in statuses if s.get('key') not in ('ASSESSMENT', 'TRAINING')]
        default_template.statuses = statuses
        default_template.save(update_fields=['statuses'])


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0018_optimize_apply_indexes'),
    ]

    operations = [
        # Schema change: add is_single_column field
        migrations.AddField(
            model_name='statuscategory',
            name='is_single_column',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'If true, HR cannot create multiple status columns under this category. '
                    'If false, HR can create unlimited sub-columns.'
                ),
            ),
        ),
        # Schema change: update key choices to include new categories
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
                ],
                help_text="Unique identifier for the category (e.g., 'HIRED', 'REJECTED')",
                max_length=50,
                unique=True,
            ),
        ),
        # Data migration: categories, flags, positions, WITHDRAWN kanban, template
        migrations.RunPython(
            add_new_categories_and_flags,
            reverse_code=reverse_new_categories_and_flags,
        ),
    ]
