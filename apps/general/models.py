import uuid

from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from utils import AbstractBaseModel
from utils.fields import UUIDField


class JobQueue(AbstractBaseModel):
    """
    Model to track RQ jobs for analytics data sending.
    Provides retry logic and monitoring for failed jobs.
    """

    class JobType(models.TextChoices):
        EDU_ANALYTICS = "edu_analytics", _("EduPartner Analytics")
        HR_ANALYTICS = "hr_analytics", _("HR Analytics")
        EMAIL_NOTIFICATION = "email_notification", _("Email Notification")
        RESUME_GENERATION = "resume_generation", _("Resume Generation")
        CANDIDATE_EVALUATION = "candidate_evaluation", _("Candidate AI Evaluation")

    class JobStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for the job"),
    )
    job_type = models.CharField(
        max_length=50,
        choices=JobType.choices,
        help_text=_("Type of the job (edu_analytics, hr_analytics, etc.)"),
    )
    target_date = models.DateField(
        help_text=_("The date the data is for"),
    )
    target_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_("ID of the target entity (faculty_id, company_id, etc.)"),
    )
    target_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Name of the target entity for easier identification"),
    )
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
        db_index=True,
        help_text=_("Current status of the job"),
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of retry attempts"),
    )
    max_retries = models.PositiveIntegerField(
        default=5,
        help_text=_("Maximum number of retries before alerting"),
    )
    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp of the last attempt"),
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        help_text=_("Error message from the last failed attempt"),
    )
    rq_job_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=_("RQ job ID for tracking"),
    )
    payload_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text=_("Hash of the payload to detect duplicates"),
    )
    alert_sent = models.BooleanField(
        default=False,
        help_text=_("Whether an alert was sent for exceeded retries"),
    )

    class Meta:
        verbose_name = _("Job Queue")
        verbose_name_plural = _("Job Queues")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["job_type", "status"]),
            models.Index(fields=["target_date", "status"]),
            models.Index(fields=["status", "retry_count"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["job_type", "target_date", "target_id"],
                name="unique_job_per_target_per_day",
            )
        ]

    def __str__(self):
        return f"{self.job_type} - {self.target_date} - {self.status}"

    def mark_processing(self):
        """Mark the job as processing."""
        self.status = self.JobStatus.PROCESSING
        self.last_attempt_at = timezone.now()
        self.save(update_fields=["status", "last_attempt_at", "updated_at"])

    def mark_completed(self):
        """Mark the job as completed."""
        self.status = self.JobStatus.COMPLETED
        self.error_message = None
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_failed(self, error_message: str):
        """Mark the job as failed with an error message."""
        self.status = self.JobStatus.FAILED
        self.error_message = error_message
        self.retry_count += 1
        self.save(update_fields=["status", "error_message", "retry_count", "updated_at"])

    @property
    def should_alert(self) -> bool:
        """Check if an alert should be sent (retry_count > max_retries and not already alerted)."""
        return self.retry_count > self.max_retries and not self.alert_sent

    @property
    def can_retry(self) -> bool:
        """Check if the job can be retried."""
        return self.retry_count < self.max_retries


class VacancyAnalyticsSync(models.Model):
    """
    Tracks whether a vacancy's deactivation (is_active=False) has been
    successfully delivered to the HR Analytics service.

    When a vacancy becomes inactive we must send one final update so HR
    Analytics knows the vacancy is closed.  After that payload is
    accepted (HTTP 200), we record the timestamp here and exclude the
    vacancy from future syncs.

    If the vacancy is later reactivated the record is cleared so it
    re-enters the normal sync cycle.
    """

    vacancy_id = models.UUIDField(
        unique=True,
        db_index=True,
        help_text=_("UUID of the vacancy being tracked"),
    )
    deactivation_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "Timestamp when is_active=False was successfully sent to HR Analytics. "
            "NULL means the final send has not yet been delivered."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Vacancy Analytics Sync")
        verbose_name_plural = _("Vacancy Analytics Syncs")
        db_table = "general_vacancy_analytics_sync"

    def __str__(self):
        return f"VacancySync({self.vacancy_id}) synced_at={self.deactivation_synced_at}"


class DomainMarketSkill(AbstractBaseModel):
    """
    Stores raw market skills collected from HH by domain or search query.
    Canonical Skill rows are created only when a candidate adds a skill or an
    admin approves a translated skill.
    """

    source = models.CharField(
        max_length=30,
        default="hh",
        db_index=True,
    )
    scope_key = models.CharField(max_length=255, db_index=True)
    domain = models.ForeignKey(
        "domain.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="market_skills",
    )
    query = models.CharField(max_length=255)
    normalized_query = models.CharField(max_length=255, db_index=True)
    area_id = models.CharField(max_length=50, default="97", db_index=True)
    language = models.CharField(max_length=5, default="uz")
    skill_name = models.CharField(max_length=255)
    normalized_skill_name = models.CharField(max_length=255, db_index=True)
    vacancy_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = _("Domain Market Skill")
        verbose_name_plural = _("Domain Market Skills")
        ordering = ["-vacancy_count", "skill_name"]
        indexes = [
            models.Index(
                fields=["source", "area_id", "scope_key", "is_active"],
                name="general_dms_source_scope_idx",
            ),
            models.Index(
                fields=["domain", "source", "is_active", "-vacancy_count"],
                name="general_dms_domain_active_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "area_id", "scope_key", "normalized_skill_name"],
                name="unique_market_skill_per_scope",
            )
        ]

    def __str__(self):
        return f"{self.skill_name} ({self.scope_key})"


class EmailTemplate(models.Model):
    """
    Represents an email template with multi-language support.
    This can be used to store reusable subjects and bodies for different email types.
    """

    LANGUAGE_CHOICES = [
        ("uz", "Uzbek"),
        ("ru", "Russian"),
        ("en", "English"),
    ]

    # The type of the template (e.g., password_reset, welcome_email, etc.)
    template_type = models.CharField(max_length=50, default="general")

    # Unique name for identifying the template
    name = models.CharField(
        max_length=100,
        help_text="Please enter the correct name, for example: 'reset-password' or 'general'",
    )

    # Language of the template (Uzbek, Russian, English)
    language = models.CharField(
        max_length=5,
        choices=LANGUAGE_CHOICES,
        default="uz",
    )

    # Subject of the email
    subject = models.CharField(max_length=200)

    # Body of the email
    body = models.FileField(
        upload_to="email_templates/",
        validators=[FileExtensionValidator(("html",))],
        help_text="Upload an HTML file for the email body.",
    )

    class Meta:
        unique_together = ("name", "language")

    def __str__(self):
        """Return a readable string representation of the template."""
        return f"{self.name} ({self.language})"


class Avatar(AbstractBaseModel):
    image = models.ImageField(
        verbose_name="Profile Picture",
        upload_to="profile/avatars/",
        validators=[FileExtensionValidator(("jpg", "jpeg", "png", "svg"))],
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Profile Avatar - {self.id}"


class ApplicationSummaryNotification(AbstractBaseModel):
    """
    Tracks which job applications have been included in recruiter summary emails.
    Prevents duplicate notifications for the same application.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Unique identifier for this notification record"),
    )
    application = models.ForeignKey(
        "applications.JobApplication",
        on_delete=models.CASCADE,
        related_name="summary_notifications",
        help_text=_("The job application that was included in a summary email"),
    )
    recruiter = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.CASCADE,
        related_name="summary_notifications",
        help_text=_("The recruiter who received the notification"),
    )
    notified_at = models.DateTimeField(
        default=timezone.now,
        help_text=_("When the notification was sent"),
    )

    class Meta:
        verbose_name = _("Application Summary Notification")
        verbose_name_plural = _("Application Summary Notifications")
        unique_together = ("application", "recruiter")
        indexes = [
            models.Index(fields=["application"]),
            models.Index(fields=["recruiter"]),
            models.Index(fields=["notified_at"]),
        ]

    def __str__(self):
        return f"Notification for {self.application_id} to {self.recruiter_id}"


class MarketSalaryCache(AbstractBaseModel):
    """
    Cached market median salary per target role.
    Refreshed periodically or when cache expires (24h TTL).
    """

    id = UUIDField(primary_key=True, version=7)
    role = models.CharField(
        max_length=255,
        db_index=True,
        help_text=_("Target role / search query, e.g. 'Python Developer'"),
    )
    source = models.CharField(
        max_length=20,
        default="both",
        help_text=_("Data source: hh, platform, both"),
    )
    median_salary_uzs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_("Market median salary in UZS"),
    )
    salary_from = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Minimum of collected salary_from values"),
    )
    salary_to = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Maximum of collected salary_to values"),
    )
    sample_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of salary data points used"),
    )

    class Meta:
        verbose_name = _("Market Salary Cache")
        verbose_name_plural = _("Market Salary Caches")
        indexes = [
            models.Index(fields=["role", "-created_at"]),
        ]

    def __str__(self):
        return f"MarketSalary(role={self.role}, median={self.median_salary_uzs} UZS, samples={self.sample_count})"


class StatUzSectorSalary(AbstractBaseModel):
    """
    Official average salary per economic sector, sourced from Uzbekistan's
    National Statistics Committee (siat.stat.uz). Used as a sanity-check band
    against the HH/platform-derived market salary estimate -- not as the
    primary source, since it's sector-level, not role-level.
    """

    class PeriodType(models.TextChoices):
        QUARTERLY = "quarterly", _("Quarterly")
        YEARLY = "yearly", _("Yearly")

    id = UUIDField(primary_key=True, version=7)
    sector_code = models.CharField(
        max_length=50,
        db_index=True,
        help_text=_("stat.uz sector classification code, matched against Domain.sector_code"),
    )
    sector_name = models.CharField(
        max_length=255,
        help_text=_("Human-readable sector name as published by stat.uz"),
    )
    period_type = models.CharField(
        max_length=20,
        choices=PeriodType.choices,
        default=PeriodType.QUARTERLY,
    )
    period_label = models.CharField(
        max_length=20,
        help_text=_("Reporting period as published, e.g. '2026-Q2' or '2025'"),
    )
    avg_salary_uzs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text=_("Average monthly salary in UZS for this sector/period"),
    )
    source_dataset_id = models.CharField(
        max_length=50,
        help_text=_("stat.uz SDMX dataset id this row was sourced from"),
    )

    class Meta:
        verbose_name = _("Stat.uz Sector Salary")
        verbose_name_plural = _("Stat.uz Sector Salaries")
        indexes = [
            models.Index(fields=["sector_code", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["sector_code", "period_type", "period_label"],
                name="unique_sector_period",
            ),
        ]

    def __str__(self):
        return f"StatUzSectorSalary(sector={self.sector_code}, period={self.period_label}, avg={self.avg_salary_uzs} UZS)"
