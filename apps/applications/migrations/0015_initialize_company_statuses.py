# Generated migration to initialize statuses for existing companies

from django.db import migrations


def initialize_company_statuses(apps, schema_editor):
    """
    Initialize statuses for all existing companies from the default template.
    
    This migration:
    1. Gets the default status template
    2. For each existing company, creates ApplicationStatusModel records
    3. Creates StatusTransitionRule records for each company
    """
    Company = apps.get_model('authentication', 'Company')
    StatusCategory = apps.get_model('applications', 'StatusCategory')
    StatusTemplate = apps.get_model('applications', 'StatusTemplate')
    ApplicationStatusModel = apps.get_model('applications', 'ApplicationStatusModel')
    StatusTransitionRule = apps.get_model('applications', 'StatusTransitionRule')
    
    # Get default template
    default_template = StatusTemplate.objects.filter(is_default=True).first()
    if not default_template:
        print("WARNING: No default template found. Skipping company status initialization.")
        return
    
    # Cache categories by key
    categories = {cat.key: cat for cat in StatusCategory.objects.all()}
    
    # Get all existing companies
    companies = Company.objects.all()
    total_companies = companies.count()
    
    if total_companies == 0:
        print("No companies found. Skipping status initialization.")
        return
    
    print(f"Initializing statuses for {total_companies} companies...")
    
    for company in companies:
        # Check if company already has statuses (in case of re-run)
        if ApplicationStatusModel.objects.filter(company=company).exists():
            print(f"  Skipping {company.name} - already has statuses")
            continue
        
        created_statuses = {}
        
        # Create statuses from template
        for status_def in default_template.statuses:
            category_key = status_def.get('category')
            category = categories.get(category_key)
            
            if not category:
                print(f"  WARNING: Category {category_key} not found, skipping status {status_def['key']}")
                continue
            
            status = ApplicationStatusModel.objects.create(
                key=status_def['key'],
                label=status_def['label'],
                company=company,
                category=category,
                color=status_def.get('color', '#6B7280'),
                position=status_def.get('position', 0),
                show_in_kanban=status_def.get('show_in_kanban', True),
                translations=status_def.get('translations', {}),
                is_default=True,
                is_active=True,
            )
            created_statuses[status_def['key']] = status
        
        # Create transition rules from template
        for rule_def in default_template.transitions:
            from_status = created_statuses.get(rule_def['from'])
            to_status = created_statuses.get(rule_def['to'])
            
            if from_status and to_status:
                StatusTransitionRule.objects.create(
                    from_status=from_status,
                    to_status=to_status,
                    recruiter_can_transition=rule_def.get('recruiter', False),
                    candidate_can_transition=rule_def.get('candidate', False),
                    is_active=True,
                )
        
        print(f"  Created {len(created_statuses)} statuses for {company.name}")
    
    print(f"Completed status initialization for {total_companies} companies.")


def reverse_company_statuses(apps, schema_editor):
    """Remove all company statuses (rollback)."""
    ApplicationStatusModel = apps.get_model('applications', 'ApplicationStatusModel')
    StatusTransitionRule = apps.get_model('applications', 'StatusTransitionRule')
    
    # Rules will be cascade-deleted when statuses are deleted
    StatusTransitionRule.objects.all().delete()
    ApplicationStatusModel.objects.all().delete()
    
    print("Removed all company statuses.")


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0014_populate_default_status_data'),
        ('authentication', '0001_initial'),  # Ensure Company model exists
    ]

    operations = [
        migrations.RunPython(
            initialize_company_statuses,
            reverse_code=reverse_company_statuses,
        ),
    ]
