"""
Data migration: Copy domain FK values to the new domains M2M relationship.
"""
from django.db import migrations


def copy_domain_fk_to_m2m(apps, schema_editor):
    """Copy existing domain FK values to the new domains M2M field."""
    AnswerChoice = apps.get_model("quiz", "AnswerChoice")
    for answer in AnswerChoice.objects.filter(domain__isnull=False).iterator():
        answer.domains.add(answer.domain)


def copy_domain_m2m_to_fk(apps, schema_editor):
    """Reverse: Copy first domain from M2M back to FK."""
    AnswerChoice = apps.get_model("quiz", "AnswerChoice")
    for answer in AnswerChoice.objects.prefetch_related("domains").iterator():
        first_domain = answer.domains.first()
        if first_domain:
            answer.domain = first_domain
            answer.save(update_fields=["domain"])


class Migration(migrations.Migration):

    dependencies = [
        ("quiz", "0004_add_domains_m2m_to_answerchoice"),
    ]

    operations = [
        migrations.RunPython(copy_domain_fk_to_m2m, copy_domain_m2m_to_fk),
    ]
