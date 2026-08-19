from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class CandidateSubscription(AbstractBaseModel):
    """
    Represents a subscription for a candidate.

    Currently a placeholder for future candidate subscription features.
    Candidates will have their own subscription plans with specific features
    (to be defined later).

    This model follows the same pattern as CompanySubscription to ensure
    consistency and easy extension when candidate subscription features
    are implemented.

    Usage:
        sub = CandidateSubscription.get_active(candidate)
        if sub:
            sub.plan.has_feature('some_candidate_feature')
    """

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")
        PENDING = "pending", _("Pending Payment")

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this subscription"),
    )
    candidate = models.ForeignKey(
        "authentication.Candidate",
        on_delete=models.CASCADE,
        related_name="subscriptions",
        help_text=_("The candidate this subscription belongs to"),
    )
    plan = models.ForeignKey(
        "subscriptions.SubscriptionPlan",
        on_delete=models.PROTECT,
        related_name="candidate_subscriptions",
        help_text=_("The subscription plan"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        help_text=_("Current status of the subscription"),
    )
    starts_at = models.DateTimeField(
        default=timezone.now,
        help_text=_("When the subscription period starts"),
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When the subscription expires. Null = no expiry (free plans)."),
    )

    # --- Future payment fields ---
    payment_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Reference to payment transaction (for future payment integration)"),
    )

    class Meta:
        verbose_name = _("Candidate Subscription")
        verbose_name_plural = _("Candidate Subscriptions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["candidate", "status"]),
        ]

    def __str__(self):
        return f"Candidate {self.candidate.email} - {self.plan.name} ({self.status})"

    @property
    def is_active(self) -> bool:
        """Check if the subscription is currently active and not expired."""
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    @classmethod
    def get_active(cls, candidate):
        """
        Get the current active subscription for a candidate.
        Returns None if no active subscription exists.
        """
        return cls.objects.filter(
            candidate=candidate,
            status=cls.Status.ACTIVE,
        ).select_related("plan").order_by("-created_at").first()

    def has_feature(self, feature_code: str) -> bool:
        """Check if the subscription plan includes a specific feature."""
        return self.plan.has_feature(feature_code)
