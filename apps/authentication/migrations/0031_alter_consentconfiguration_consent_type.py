# Generated migration for adding public_offer consent type

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0030_alter_candidate_onboarding_progress"),
    ]

    operations = [
        migrations.AlterField(
            model_name="consentconfiguration",
            name="consent_type",
            field=models.CharField(
                choices=[
                    ("terms_of_service", "Terms of Service"),
                    ("privacy_policy", "Privacy Policy"),
                    ("data_processing", "Data Processing Agreement"),
                    ("company_terms", "Company Terms and Conditions"),
                    ("public_offer", "Public Offer"),
                ],
                help_text="Type of consent (e.g., terms_of_service, privacy_policy)",
                max_length=50,
            ),
        ),
    ]
