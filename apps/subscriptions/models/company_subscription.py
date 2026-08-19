from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class CompanySubscription(AbstractBaseModel):
    """
    Represents an active subscription for a company.

    Each company has exactly one active subscription at a time.
    When a company is created, it is automatically assigned the free plan.

    Lifecycle:
    1. Company registers → free CompanySubscription created automatically
    2. Admin purchases upgrade → new subscription replaces the old one
    3. Subscription expires → company reverts to free plan (future logic)

    Usage:
        sub = CompanySubscription.get_active(company)
        sub.plan.name  # 'Free'
        sub.can_add_recruiter()  # True/False based on limits
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
    company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.CASCADE,
        related_name="subscriptions",
        help_text=_("The company this subscription belongs to"),
    )
    plan = models.ForeignKey(
        "subscriptions.SubscriptionPlan",
        on_delete=models.PROTECT,
        related_name="company_subscriptions",
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
    has_design = models.BooleanField(
        default=False,
        help_text=_("Enable branded design for this company's vacancies (banner + styled cards)."),
    )

    # --- Future payment fields ---
    payment_reference = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Reference to payment transaction (for future payment integration)"),
    )

    class Meta:
        verbose_name = _("Company Subscription")
        verbose_name_plural = _("Company Subscriptions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self):
        return f"{self.company.name} - {self.plan.name} ({self.status})"

    @property
    def is_active(self) -> bool:
        """Check if the subscription is currently active and not expired."""
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    @classmethod
    def get_active(cls, company):
        """
        Get the current active subscription for a company.
        Returns None if no active subscription exists.
        """
        return cls.objects.filter(
            company=company,
            status=cls.Status.ACTIVE,
        ).select_related("plan").order_by("-created_at").first()

    def has_feature(self, feature_code: str) -> bool:
        """Check if the subscription plan includes a specific feature."""
        return self.plan.has_feature(feature_code)


class SubscriptionSeatAssignment(AbstractBaseModel):
    """
    Tracks which recruiters have been assigned seats under a company subscription.

    After purchasing a subscription, the company admin assigns specific recruiters
    to available seats. Only assigned recruiters get access to subscription features.

    Seat types:
    - 'admin': Admin-level seat (limited by plan.max_admins)
    - 'recruiter': Recruiter-level seat (limited by plan.max_recruiters)

    Business rules:
    - Total admin seats assigned ≤ plan.max_admins
    - Total recruiter seats assigned ≤ plan.max_recruiters
    - A recruiter can only have one active seat per subscription
    - Deactivated seats free up the slot for reassignment

    Usage:
        # Check if a recruiter has an active seat
        has_seat = SubscriptionSeatAssignment.objects.filter(
            subscription__company=company,
            recruiter=recruiter,
            is_active=True,
        ).exists()
    """

    class SeatType(models.TextChoices):
        ADMIN = "admin", _("Admin")
        RECRUITER = "recruiter", _("Recruiter")

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this seat assignment"),
    )
    subscription = models.ForeignKey(
        CompanySubscription,
        on_delete=models.CASCADE,
        related_name="seat_assignments",
        help_text=_("The subscription this seat belongs to"),
    )
    recruiter = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.CASCADE,
        related_name="subscription_seats",
        help_text=_("The recruiter assigned to this seat"),
    )
    seat_type = models.CharField(
        max_length=20,
        choices=SeatType.choices,
        help_text=_("Whether this is an admin or recruiter seat"),
    )
    is_active = models.BooleanField(
        default=True,
        help_text=_("Whether this seat assignment is currently active"),
    )

    class Meta:
        verbose_name = _("Seat Assignment")
        verbose_name_plural = _("Seat Assignments")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "recruiter"],
                condition=models.Q(is_active=True),
                name="unique_active_seat_per_recruiter",
            ),
        ]
        indexes = [
            models.Index(fields=["subscription", "seat_type", "is_active"]),
            models.Index(fields=["recruiter", "is_active"]),
        ]

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return (
            f"{self.recruiter.email} - {self.get_seat_type_display()} "
            f"({status})"
        )
