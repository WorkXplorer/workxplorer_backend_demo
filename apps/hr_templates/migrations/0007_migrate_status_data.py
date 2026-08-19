# Data migration: Map legacy status values to ApplicationStatusModel

from django.db import migrations


def migrate_legacy_statuses(apps, schema_editor):
    """
    Map legacy Reason.status values to ApplicationStatusModel entries.
    
    Mapping:
    - REJECTED → company's default status with category=REJECTED
    - OFFERED → company's default status with category=OFFERED
    - INTERVIEW_SCHEDULED → company's default status with category=INTERVIEWING
    """
    Template = apps.get_model("hr_templates", "Template")
    ApplicationStatusModel = apps.get_model("applications", "ApplicationStatusModel")
    StatusCategory = apps.get_model("applications", "StatusCategory")

    # Get or create status categories
    category_map = {
        "REJECTED": StatusCategory.objects.filter(key="REJECTED").first(),
        "OFFERED": StatusCategory.objects.filter(key="OFFERED").first(),
        "INTERVIEW_SCHEDULED": StatusCategory.objects.filter(key="INTERVIEWING").first(),
    }

    # Process each template with a legacy status
    for template in Template.objects.filter(status__isnull=False):
        category = category_map.get(template.status)
        if not category:
            continue

        # Find the company's default status for this category
        # Prefer is_default=True, otherwise take the first active one
        status = ApplicationStatusModel.objects.filter(
            company=template.company,
            category=category,
            is_active=True,
        ).order_by("-is_default", "position").first()

        if status:
            template.application_status = status
            template.save(update_fields=["application_status"])


def reverse_migrate_legacy_statuses(apps, schema_editor):
    """Reverse migration: clear application_status fields."""
    Template = apps.get_model("hr_templates", "Template")
    Template.objects.all().update(application_status=None)


class Migration(migrations.Migration):

    dependencies = [
        ("hr_templates", "0006_add_template_fields"),
    ]

    operations = [
        migrations.RunPython(
            migrate_legacy_statuses,
            reverse_migrate_legacy_statuses,
        ),
    ]
