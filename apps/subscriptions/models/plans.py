from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class SubscriptionPlan(AbstractBaseModel):
    """
    Defines a subscription plan (tier) for either companies or candidates.

    Company tiers: free, basic, pro
    Candidate tiers: free (more to come later)

    Each plan defines:
    - Resource limits (max admins, max recruiters) for company plans
    - Price and billing info (prepared for future payment integration)
    - Which features are available (via PlanFeature M2M)

    Usage:
        plan = SubscriptionPlan.objects.get(slug='company-basic')
        plan.max_admins  # 2
        plan.max_recruiters  # 5
        plan.has_feature('headhunting_access')  # True
    """

    class PlanType(models.TextChoices):
        COMPANY = "company", _("Company")
        CANDIDATE = "candidate", _("Candidate")

    class BillingPeriod(models.TextChoices):
        MONTHLY = "monthly", _("Monthly")
        YEARLY = "yearly", _("Yearly")
        LIFETIME = "lifetime", _("Lifetime")

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this plan"),
    )
    name = models.CharField(
        max_length=100,
        help_text=_("Display name of the plan (e.g., 'Free', 'Basic', 'Pro')"),
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text=_(
            "URL-friendly identifier (e.g., 'company-free', 'company-basic'). "
            "Used in code to reference specific plans."
        ),
    )
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        help_text=_("Whether this plan is for companies or candidates"),
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text=_("Detailed description of what this plan offers"),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this plan is currently available for purchase/assignment"),
    )

    # --- Resource limits (Company plans) ---
    max_admins = models.PositiveIntegerField(
        default=1,
        help_text=_(
            "Maximum number of admin-level recruiters allowed. "
            "Only relevant for company plans."
        ),
    )
    max_recruiters = models.PositiveIntegerField(
        default=3,
        help_text=_(
            "Maximum number of recruiter-level users allowed. "
            "Only relevant for company plans."
        ),
    )

    # --- Pricing (prepared for future payment integration) ---
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("Price of this plan (0 for free plans)"),
    )
    billing_period = models.CharField(
        max_length=20,
        choices=BillingPeriod.choices,
        null=True,
        blank=True,
        help_text=_("Billing cycle for paid plans. Null for free plans."),
    )

    # --- Feature M2M ---
    features = models.ManyToManyField(
        "subscriptions.SubscriptionFeature",
        through="subscriptions.PlanFeature",
        related_name="plans",
        blank=True,
        help_text=_("Features included in this plan"),
    )

    # --- Display ordering ---
    display_order = models.PositiveIntegerField(
        default=0,
        help_text=_("Order in which plans are displayed (lower = first)"),
    )

    class Meta:
        verbose_name = _("Subscription Plan")
        verbose_name_plural = _("Subscription Plans")
        ordering = ["display_order", "price"]
        indexes = [
            models.Index(fields=["plan_type", "is_active"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_plan_type_display()})"

    def has_feature(self, feature_code: str) -> bool:
        """
        Check if this plan includes a specific feature.

        Args:
            feature_code: The unique code of the feature (e.g., 'headhunting_access')

        Returns:
            True if the plan includes the feature and it is enabled.
        """
        return self.plan_features.filter(
            feature__code=feature_code,
            is_enabled=True,
        ).exists()

    @property
    def total_seats(self) -> int:
        """Total number of user seats (admins + recruiters) for company plans."""
        return self.max_admins + self.max_recruiters


class SubscriptionFeature(AbstractBaseModel):
    """
    Defines a feature that can be attached to subscription plans.

    Features are identified by a unique `code` used in permission checks.
    Each feature belongs to a type (company/candidate) for filtering.

    Predefined company features:
    - 'company_analytics': Access to company-level analytics
    - 'full_analytics': Access to full/advanced analytics
    - 'headhunting_access': Ability to contact unresponded candidates

    Usage:
        # Check if a company has headhunting access
        company_sub = CompanySubscription.objects.get(company=company)
        has_access = company_sub.plan.has_feature('headhunting_access')
    """

    class FeatureType(models.TextChoices):
        COMPANY = "company", _("Company")
        CANDIDATE = "candidate", _("Candidate")

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this feature"),
    )
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text=_(
            "Unique code identifier used in permission checks "
            "(e.g., 'headhunting_access', 'company_analytics')"
        ),
    )
    name = models.CharField(
        max_length=255,
        help_text=_("Human-readable name of the feature"),
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text=_("Description of what this feature provides"),
    )
    feature_type = models.CharField(
        max_length=20,
        choices=FeatureType.choices,
        help_text=_("Whether this feature applies to company or candidate plans"),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this feature is currently in use"),
    )

    class Meta:
        verbose_name = _("Subscription Feature")
        verbose_name_plural = _("Subscription Features")
        ordering = ["feature_type", "name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["feature_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class PlanFeature(AbstractBaseModel):
    """
    Links a SubscriptionPlan to a SubscriptionFeature.

    This through-model allows:
    - Enabling/disabling a feature for a specific plan
    - Storing per-plan configuration for a feature (via `configuration` JSON)

    Example configuration values:
    - {"max_invitations_per_day": 50}
    - {"analytics_retention_days": 90}
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this plan-feature link"),
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        related_name="plan_features",
        help_text=_("The subscription plan"),
    )
    feature = models.ForeignKey(
        SubscriptionFeature,
        on_delete=models.CASCADE,
        related_name="plan_features",
        help_text=_("The feature included in this plan"),
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text=_("Whether this feature is enabled for this plan"),
    )
    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Optional JSON configuration for this feature within the plan. "
            "e.g., {'max_invitations_per_day': 50}"
        ),
    )

    class Meta:
        verbose_name = _("Plan Feature")
        verbose_name_plural = _("Plan Features")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "feature"],
                name="unique_plan_feature",
            ),
        ]

    def __str__(self):
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.plan.name} - {self.feature.name} ({status})"
