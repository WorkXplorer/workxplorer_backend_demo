from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class CandidateFeatureUsage(AbstractBaseModel):
    """
    Tracks per-feature usage counts on a calendar-month basis.

    Used to enforce subscription-based limits (e.g. AI resume
    generations per month based on the candidate's plan).

    The ``usage_month`` is always normalised to the first day of
    the month so that lookups and resets are simple.
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this usage record"),
    )
    candidate = models.ForeignKey(
        "authentication.Candidate",
        on_delete=models.CASCADE,
        related_name="feature_usage",
        help_text=_("The candidate whose usage is being tracked"),
    )
    feature = models.ForeignKey(
        "subscriptions.SubscriptionFeature",
        on_delete=models.CASCADE,
        related_name="candidate_usage",
        help_text=_("The feature being tracked (e.g. ai_resume_generation)"),
    )
    usage_month = models.DateField(
        help_text=_("First day of the calendar month this usage belongs to"),
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of times this feature was used in this month"),
    )

    class Meta:
        verbose_name = _("Candidate Feature Usage")
        verbose_name_plural = _("Candidate Feature Usage")
        ordering = ["-usage_month", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "feature", "usage_month"],
                name="unique_candidate_feature_usage_month",
            ),
        ]
        indexes = [
            models.Index(fields=["candidate", "feature"]),
            models.Index(fields=["usage_month"]),
        ]

    def __str__(self):
        return (
            f"Candidate {self.candidate_id} - "
            f"{self.feature.code} - "
            f"{self.usage_month}: {self.usage_count}"
        )

    @classmethod
    def increment_usage(cls, candidate, feature, usage_date=None):
        """
        Atomically increment (or create) the usage count for a given
        candidate, feature, and calendar month.

        Args:
            candidate: Candidate instance.
            feature: SubscriptionFeature instance.
            usage_date: Date within the target month (defaults to today).

        Returns:
            Tuple of (CandidateFeatureUsage, created: bool).
        """
        from datetime import date

        if usage_date is None:
            usage_date = date.today()

        month_start = usage_date.replace(day=1)

        record, created = cls.objects.get_or_create(
            candidate=candidate,
            feature=feature,
            usage_month=month_start,
            defaults={"usage_count": 1},
        )

        if not created:
            record.usage_count = models.F("usage_count") + 1
            record.save(update_fields=["usage_count", "updated_at"])
            record.refresh_from_db(fields=["usage_count"])

        return record, created


class CompanyFeatureUsage(AbstractBaseModel):
    """
    Tracks per-feature usage counts for companies on a calendar-month basis.

    Used to enforce subscription-based limits (e.g. AI template
    generations per month based on the company's plan).
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this usage record"),
    )
    company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.CASCADE,
        related_name="feature_usage",
        help_text=_("The company whose usage is being tracked"),
    )
    feature = models.ForeignKey(
        "subscriptions.SubscriptionFeature",
        on_delete=models.CASCADE,
        related_name="company_usage",
        help_text=_("The feature being tracked (e.g. ai_template_generation)"),
    )
    usage_month = models.DateField(
        help_text=_("First day of the calendar month this usage belongs to"),
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of times this feature was used in this month"),
    )

    class Meta:
        verbose_name = _("Company Feature Usage")
        verbose_name_plural = _("Company Feature Usage")
        ordering = ["-usage_month", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "feature", "usage_month"],
                name="unique_company_feature_usage_month",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "feature"]),
            models.Index(fields=["usage_month"]),
        ]

    def __str__(self):
        return (
            f"Company {self.company_id} - "
            f"{self.feature.code} - "
            f"{self.usage_month}: {self.usage_count}"
        )

    @classmethod
    def increment_usage(cls, company, feature, usage_date=None):
        """
        Atomically increment (or create) the usage count for a given
        company, feature, and calendar month.
        """
        from datetime import date

        if usage_date is None:
            usage_date = date.today()

        month_start = usage_date.replace(day=1)

        record, created = cls.objects.get_or_create(
            company=company,
            feature=feature,
            usage_month=month_start,
            defaults={"usage_count": 1},
        )

        if not created:
            record.usage_count = models.F("usage_count") + 1
            record.save(update_fields=["usage_count", "updated_at"])
            record.refresh_from_db(fields=["usage_count"])

        return record, created

    @classmethod
    def current_usage(cls, company, feature, usage_date=None):
        """Return the usage count for the company/feature in the current month."""
        from datetime import date

        if feature is None:
            return 0
        if usage_date is None:
            usage_date = date.today()
        month_start = usage_date.replace(day=1)
        record = cls.objects.filter(
            company=company,
            feature=feature,
            usage_month=month_start,
        ).first()
        return record.usage_count if record else 0
