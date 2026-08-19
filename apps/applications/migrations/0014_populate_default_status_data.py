# Generated migration for populating default status categories and template

from django.db import migrations


def create_default_categories(apps, schema_editor):
    """Create the 8 system-defined status categories for analytics."""
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    
    categories = [
        {
            'key': 'APPLIED',
            'label': 'Applied',
            'description': 'Initial application received. Entry point for all candidates.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'position': 1,
        },
        {
            'key': 'SCREENING',
            'label': 'Screening',
            'description': 'Under review, initial filtering. Resume screening, phone screens, etc.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'position': 2,
        },
        {
            'key': 'INTERVIEWING',
            'label': 'Interviewing',
            'description': 'Active interview process. Candidate has completed at least one interview.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'position': 3,
        },
        {
            'key': 'OFFERED',
            'label': 'Offered',
            'description': 'Offer extended to candidate. Waiting for candidate response.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'position': 4,
        },
        {
            'key': 'HIRED',
            'label': 'Hired',
            'description': 'Offer accepted. Candidate will join the company. Critical for analytics (time-to-hire, conversion).',
            'is_terminal': True,
            'is_positive_outcome': True,
            'position': 5,
        },
        {
            'key': 'REJECTED',
            'label': 'Rejected',
            'description': 'Application declined by company. Terminal negative state.',
            'is_terminal': True,
            'is_positive_outcome': False,
            'position': 6,
        },
        {
            'key': 'WITHDRAWN',
            'label': 'Withdrawn',
            'description': 'Candidate withdrew their application.',
            'is_terminal': True,
            'is_positive_outcome': False,
            'position': 7,
        },
        {
            'key': 'ON_HOLD',
            'label': 'On Hold',
            'description': 'Process temporarily paused. Can be resumed later.',
            'is_terminal': False,
            'is_positive_outcome': False,
            'position': 8,
        },
    ]
    
    for cat_data in categories:
        StatusCategory.objects.create(**cat_data)


def create_default_template(apps, schema_editor):
    """Create the default status template for new companies."""
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')
    
    # Define default statuses matching the current hardcoded ones
    statuses = [
        {
            'key': 'APPLIED',
            'label': 'Applied',
            'category': 'APPLIED',
            'color': '#3B82F6',  # Blue
            'position': 1,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Подано',
                'uz': 'Topshirildi',
            },
        },
        {
            'key': 'INTERVIEW_SCHEDULED',
            'label': 'Interview Scheduled',
            'category': 'SCREENING',
            'color': '#8B5CF6',  # Purple
            'position': 2,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Собеседование назначено',
                'uz': 'Suhbat belgilandi',
            },
        },
        {
            'key': 'INTERVIEWED',
            'label': 'Interviewed',
            'category': 'INTERVIEWING',
            'color': '#10B981',  # Green
            'position': 3,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Собеседование пройдено',
                'uz': "Suhbat o'tkazildi",
            },
        },
        {
            'key': 'OFFERED',
            'label': 'Offered',
            'category': 'OFFERED',
            'color': '#F59E0B',  # Amber
            'position': 4,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Предложение сделано',
                'uz': 'Taklif berildi',
            },
        },
        {
            'key': 'OFFER_ACCEPTED',
            'label': 'Offer Accepted',
            'category': 'HIRED',
            'color': '#22C55E',  # Green
            'position': 5,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Предложение принято',
                'uz': 'Taklif qabul qilindi',
            },
        },
        {
            'key': 'OFFER_REJECTED',
            'label': 'Offer Rejected',
            'category': 'REJECTED',
            'color': '#EF4444',  # Red
            'position': 6,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Предложение отклонено',
                'uz': 'Taklif rad etildi',
            },
        },
        {
            'key': 'WITHDRAWN',
            'label': 'Withdrawn',
            'category': 'WITHDRAWN',
            'color': '#6B7280',  # Gray
            'position': 7,
            'show_in_kanban': False,  # Hidden from kanban board
            'translations': {
                'ru': 'Отозвано',
                'uz': 'Qaytarib olindi',
            },
        },
        {
            'key': 'REJECTED',
            'label': 'Rejected',
            'category': 'REJECTED',
            'color': '#DC2626',  # Dark red
            'position': 8,
            'show_in_kanban': True,
            'translations': {
                'ru': 'Отклонено',
                'uz': 'Rad etildi',
            },
        },
    ]
    
    # Define transition rules matching the current business logic
    # Format: {from_status: [(to_status, recruiter_can, candidate_can), ...]}
    transitions = [
        # From APPLIED
        {'from': 'APPLIED', 'to': 'INTERVIEW_SCHEDULED', 'recruiter': True, 'candidate': False},
        {'from': 'APPLIED', 'to': 'OFFERED', 'recruiter': True, 'candidate': False},
        {'from': 'APPLIED', 'to': 'REJECTED', 'recruiter': True, 'candidate': False},
        {'from': 'APPLIED', 'to': 'WITHDRAWN', 'recruiter': False, 'candidate': True},
        
        # From INTERVIEW_SCHEDULED
        {'from': 'INTERVIEW_SCHEDULED', 'to': 'INTERVIEWED', 'recruiter': True, 'candidate': False},
        {'from': 'INTERVIEW_SCHEDULED', 'to': 'OFFERED', 'recruiter': True, 'candidate': False},
        {'from': 'INTERVIEW_SCHEDULED', 'to': 'REJECTED', 'recruiter': True, 'candidate': False},
        
        # From INTERVIEWED
        {'from': 'INTERVIEWED', 'to': 'OFFERED', 'recruiter': True, 'candidate': False},
        {'from': 'INTERVIEWED', 'to': 'REJECTED', 'recruiter': True, 'candidate': False},
        
        # From OFFERED - ONLY candidate can accept/reject
        {'from': 'OFFERED', 'to': 'OFFER_ACCEPTED', 'recruiter': False, 'candidate': True},
        {'from': 'OFFERED', 'to': 'OFFER_REJECTED', 'recruiter': False, 'candidate': True},
        {'from': 'OFFERED', 'to': 'REJECTED', 'recruiter': True, 'candidate': False},
        
        # From WITHDRAWN - only candidate can reapply
        {'from': 'WITHDRAWN', 'to': 'APPLIED', 'recruiter': False, 'candidate': True},
        
        # Terminal states (OFFER_ACCEPTED, OFFER_REJECTED, REJECTED) have no outgoing transitions
    ]
    
    StatusTemplate.objects.create(
        name='Standard Hiring Process',
        description='Default hiring workflow with 8 statuses: Applied → Interview Scheduled → '
                    'Interviewed → Offered → Offer Accepted/Rejected. Includes Withdrawn and Rejected states. '
                    'This template matches the original WorkXplorer application status flow.',
        is_default=True,
        is_active=True,
        statuses=statuses,
        transitions=transitions,
    )


def reverse_default_data(apps, schema_editor):
    """Remove default data for rollback."""
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')
    
    StatusTemplate.objects.filter(name='Standard Hiring Process').delete()
    StatusCategory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0013_add_flexible_status_system'),
    ]

    operations = [
        migrations.RunPython(
            create_default_categories,
            reverse_code=reverse_default_data,
        ),
        migrations.RunPython(
            create_default_template,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
