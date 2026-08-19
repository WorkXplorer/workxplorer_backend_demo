# Generated migration to initialize kanban_position for existing applications

from django.db import migrations


def initialize_kanban_positions(apps, schema_editor):
    """
    Initialize kanban_position for all existing applications.
    
    Positions are company-wide and status-scoped.
    For each company and status combination:
    1. Sort applications by applied_at (most recent first)
    2. Assign position 0 to the most recent, incrementing for older ones
    
    This ensures existing data has meaningful positions when the Kanban board is first used.
    """
    JobApplication = apps.get_model('applications', 'JobApplication')
    
    # Get all unique (company, status) combinations
    company_status_combinations = JobApplication.objects.values_list(
        'vacancy__company', 'status'
    ).distinct()
    
    for company_id, status in company_status_combinations:
        # Get all applications for this company and status, ordered by applied_at (most recent first)
        applications = list(JobApplication.objects.filter(
            vacancy__company_id=company_id,
            status=status
        ).order_by('-applied_at'))
        
        # Assign positions: 0 for most recent, incrementing for older ones
        for position, application in enumerate(applications):
            application.kanban_position = position
        
        # Bulk update for efficiency
        if applications:
            JobApplication.objects.bulk_update(applications, ['kanban_position'], batch_size=500)


def reverse_kanban_positions(apps, schema_editor):
    """
    Reverse operation: reset all kanban_position to 0.
    """
    JobApplication = apps.get_model('applications', 'JobApplication')
    JobApplication.objects.all().update(kanban_position=0)


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0008_add_kanban_position'),
    ]

    operations = [
        migrations.RunPython(initialize_kanban_positions, reverse_kanban_positions),
    ]
