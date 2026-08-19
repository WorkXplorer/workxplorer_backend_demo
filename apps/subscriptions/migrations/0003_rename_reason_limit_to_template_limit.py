from django.db import migrations


def rename_reason_limit_to_template_limit(apps, schema_editor):
    SubscriptionFeature = apps.get_model("subscriptions", "SubscriptionFeature")
    SubscriptionFeature.objects.filter(code="reason_limit").update(code="template_limit")


def reverse_rename(apps, schema_editor):
    SubscriptionFeature = apps.get_model("subscriptions", "SubscriptionFeature")
    SubscriptionFeature.objects.filter(code="template_limit").update(code="reason_limit")


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0002_candidatefeatureusage"),
    ]

    operations = [
        migrations.RunPython(
            rename_reason_limit_to_template_limit,
            reverse_code=reverse_rename,
        ),
    ]
