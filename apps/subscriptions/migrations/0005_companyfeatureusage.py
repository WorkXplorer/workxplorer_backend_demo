import django.db.models.deletion
import utils.fields.uuid7_field
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0033_customuser_preferred_language"),
        ("subscriptions", "0004_ai_template_generation_feature"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyFeatureUsage",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated at"),
                ),
                (
                    "id",
                    utils.fields.uuid7_field.UUIDField(
                        default=utils.fields.uuid7_field.uuidv7,
                        editable=False,
                        help_text="Unique identifier for this usage record",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "usage_month",
                    models.DateField(
                        help_text="First day of the calendar month this usage belongs to"
                    ),
                ),
                (
                    "usage_count",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Number of times this feature was used in this month",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        help_text="The company whose usage is being tracked",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_usage",
                        to="authentication.company",
                    ),
                ),
                (
                    "feature",
                    models.ForeignKey(
                        help_text="The feature being tracked (e.g. ai_template_generation)",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="company_usage",
                        to="subscriptions.subscriptionfeature",
                    ),
                ),
            ],
            options={
                "verbose_name": "Company Feature Usage",
                "verbose_name_plural": "Company Feature Usage",
                "ordering": ["-usage_month", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["company", "feature"],
                        name="subscriptio_company_cfu_idx",
                    ),
                    models.Index(
                        fields=["usage_month"], name="subscriptio_cfu_month_idx"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("company", "feature", "usage_month"),
                        name="unique_company_feature_usage_month",
                    )
                ],
            },
        ),
    ]
