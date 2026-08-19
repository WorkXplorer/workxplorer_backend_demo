from django.db import migrations

FEATURE_CODE = "ai_template_generation"


def create_feature(apps, schema_editor):
    SubscriptionFeature = apps.get_model("subscriptions", "SubscriptionFeature")
    SubscriptionFeature.objects.update_or_create(
        code=FEATURE_CODE,
        defaults={
            "name": "AI Template Generation",
            "description": (
                "Allows AI-powered drafting of HR message templates "
                "(invitation / interview / rejection)."
            ),
            "feature_type": "company",
            "is_active": True,
        },
    )


def remove_feature(apps, schema_editor):
    SubscriptionFeature = apps.get_model("subscriptions", "SubscriptionFeature")
    SubscriptionFeature.objects.filter(code=FEATURE_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0004_merge_20260627_1730"),
    ]

    operations = [
        migrations.RunPython(create_feature, remove_feature),
    ]
