import contextlib
import os
import logging
from utils.fields import UUIDField
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from .choices import ApplicationStatus, ApplicationDocumentTypes
from utils import AbstractBaseModel
from apps.resumes.models.choices import WorkStatus

logger = logging.getLogger(__name__)


class JobApplication(AbstractBaseModel):
    """
    Represents a candidate's application to a specific vacancy.

    This model serves as the central hub for tracking all interactions
    between a candidate and a specific job opening. Think of it as
    the digital equivalent of a physical application folder that
    HR departments used to maintain for each applicant.
    """

    # Primary identifiers
    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text="Unique identifier for this application",
    )

    candidate = models.ForeignKey(
        "authentication.Candidate",
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="The candidate who submitted this application",
    )

    vacancy = models.ForeignKey(
        "vacancies.Vacancy",
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="The job vacancy this application is for",
    )

    applied_at = models.DateTimeField(
        default=timezone.now, help_text="When the candidate submitted their application"
    )

    updated_at = models.DateTimeField(
        auto_now=True, help_text="When this application was last modified"
    )

    status = models.CharField(
        max_length=50,
        default=ApplicationStatus.APPLIED,
        help_text="Current status of this application in the hiring process",
    )

    resume_used = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
        help_text="The specific resume version used for this application",
    )

    cover_letter = models.TextField(
        blank=True, help_text="Optional cover letter submitted with this application"
    )

    portfolio_url = models.URLField(
        blank=True,
        max_length=500,
        help_text="Optional portfolio or personal website URL",
    )

    additional_documents = models.JSONField(
        default=dict,
        blank=True,
        help_text="Store references to additional documents (file paths, URLs, etc.)",
    )

    recruiter_notes = models.TextField(
        blank=True,
        help_text="Internal notes for recruiters (not visible to candidates)",
    )

    earliest_start_date = models.DateField(
        null=True, blank=True, help_text="When the candidate can start working"
    )

    is_active = models.BooleanField(
        default=True, help_text="Whether this application is still active in the system"
    )

    last_updated_by = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_applications",
        help_text="The recruiter who last updated this application",
    )

    in_review_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the application status changed from 'Applied' to 'Under Review'",
    )

    hired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the application status changed to 'Accepted' (hired date)",
    )

    kanban_position = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text="Position of the application in the Kanban board column. "
                  "Lower values appear first. Used for drag-and-drop reordering.",
    )

    is_demo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="If True, this application is demo/placeholder data shown to unapproved companies.",
    )

    class Meta:
        # Ensure a candidate can only apply once to each vacancy
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "vacancy"],
                name="unique_candidate_vacancy_application",
            )
        ]

        # Database indexes for common query patterns
        indexes = [
            models.Index(fields=["candidate"]),
            models.Index(fields=["vacancy"]),
            models.Index(fields=["status"]),
            models.Index(fields=["applied_at"]),
            models.Index(
                fields=["vacancy", "status"]
            ),  # Compound index for recruiter dashboards
            models.Index(
                fields=["candidate", "status"]
            ),  # Compound index for candidate dashboards
            models.Index(
                fields=["status", "kanban_position"]
            ),  # Compound index for Kanban board ordering
            models.Index(
                fields=["status", "vacancy", "kanban_position"]
            ),  # Speeds up new-application column placement lookups
        ]

        ordering = ["-applied_at"]

        verbose_name = "Job Application"
        verbose_name_plural = "Job Applications"

    def __str__(self):
        return f"{self.candidate} → {self.vacancy.title} ({self.get_status_display()})"

    def get_status_display(self, language: str | None = None) -> str:
        """
        Return a human-readable status label.

        Supports both legacy enum statuses and flexible company-specific statuses.
        """
        from apps.applications.models import ApplicationStatusModel
        from apps.applications.models.choices import ApplicationStatus

        # First resolve legacy enum labels without touching the database.
        with contextlib.suppress(ValueError):
            status_choice = ApplicationStatus(self.status)
            if language:
                translations = ApplicationStatus.get_translations()
                return translations[status_choice].get(
                    language,
                    translations[status_choice]["en"],
                )
            return status_choice.label

        # Then try company-specific flexible statuses.
        with contextlib.suppress(Exception):
            status_model = ApplicationStatusModel.objects.filter(
                company=self.vacancy.company,
                key=self.status,
            ).only("label", "translations").first()
            if status_model:
                if language and language != "en":
                    return status_model.translations.get(language, status_model.label)
                return status_model.label

        # Last resort for unknown values.
        return str(self.status).replace("_", " ").title()

    def clean(self):
        """
        Custom validation logic that runs before saving.

        This is where we can add business rules that involve
        multiple fields or complex validation logic.
        """
        super().clean()

        # Ensure earliest_start_date is not in the past (unless status is already advanced)
        if (
                self.earliest_start_date
                and self.earliest_start_date < timezone.now().date()
                and self.status == ApplicationStatus.APPLIED
        ):
            raise ValidationError(
                "Start date cannot be in the past for new applications"
            )

    def _is_hired_status(self) -> bool:
        """
        Check if the current status represents a hired candidate.

        Uses the flexible status system (HIRED category) when available,
        falls back to checking for OFFER_ACCEPTED.

        ``perform_update`` may set ``_cached_is_hired`` on the instance before
        calling ``save()`` to avoid a redundant ApplicationStatusModel query.
        """
        # Fast path: use caller-provided value to skip the DB round-trip.
        cached = getattr(self, '_cached_is_hired', None)
        if cached is not None:
            return cached

        from apps.applications.models import ApplicationStatusModel, StatusCategory
        
        try:
            company = self.vacancy.company
            status_model = ApplicationStatusModel.objects.filter(
                company=company,
                key=self.status,
                is_active=True,
            ).select_related('category').first()
            
            if status_model:
                return status_model.category.key == StatusCategory.HIRED
        except Exception as e:
            logger.warning(
                f"Failed to check hired status using flexible system for "
                f"application {self.id}, falling back to legacy: {e}"
            )
        
        # Fall back to legacy check
        # ponytail: ApplicationStatus.HIRED doesn't exist in TextChoices — use OFFER_ACCEPTED
        return self.status == ApplicationStatus.OFFER_ACCEPTED

    def save(self, *args, **kwargs):
        """
        Override save to add custom logic when applications are created or updated.

        ``perform_update`` may set ``_cached_old_status`` on the instance before
        calling ``save()`` to avoid a redundant ``JobApplication.objects.get()``
        query that would otherwise be used to detect the previous status.
        """
        skip_full_clean = kwargs.pop("skip_full_clean", False)
        is_hired_status = self._is_hired_status()

        # UUID primary keys are assigned before the first INSERT, so ``self.pk``
        # cannot distinguish create from update here. Use Django's state flag.
        if not self._state.adding:
            cached_old_status = getattr(self, '_cached_old_status', None)
            if cached_old_status is not None:
                # Caller already knows the previous status — no DB query needed.
                if cached_old_status != self.status:
                    self.updated_at = timezone.now()
                    if (
                        cached_old_status == ApplicationStatus.APPLIED
                        and self.status != ApplicationStatus.APPLIED
                        and self.in_review_at is None
                    ):
                        self.in_review_at = timezone.now()
                    if is_hired_status and self.hired_at is None:
                        self.hired_at = timezone.now()
            else:
                with contextlib.suppress(JobApplication.DoesNotExist):
                    old_instance = JobApplication.objects.get(pk=self.pk)
                    if old_instance.status != self.status:
                        self.updated_at = timezone.now()
                        # Set in_review_at when moving from APPLIED to any status beyond APPLIED
                        if (
                                old_instance.status == ApplicationStatus.APPLIED
                                and self.status != ApplicationStatus.APPLIED
                                and self.in_review_at is None  # Only set if not already set
                        ):
                            self.in_review_at = timezone.now()
                        # Set hired_at when status changes to a HIRED category status
                        if is_hired_status and self.hired_at is None:
                            self.hired_at = timezone.now()

        # Skip model-level validation only when the caller already validated the
        # instance and wants to avoid repeating the same existence/constraint
        # checks during save().
        if not skip_full_clean:
            self.full_clean()

        # Call the parent save method
        super().save(*args, **kwargs)

        # Update resume employment info when candidate is hired
        if is_hired_status:
            self._update_resume_employment_info()

    def _update_resume_employment_info(self):
        """
        Update the candidate's resume employment information when offer is accepted.
        
        This method:
        1. Updates the work_status to EMPLOYED on the resume_used or main resume
        2. Updates employment tracking fields on the main resume (is_main=True)
        """
        from apps.resumes.models import Resume

        # Get the vacancy to extract company information
        vacancy = self.vacancy

        # Determine which resume to update for work_status
        # Priority: resume_used if exists, otherwise find main resume
        if self.resume_used:
            # Update work_status on the resume that was used for application
            self.resume_used.work_status = WorkStatus.EMPLOYED
            self.resume_used.save(update_fields=['work_status'])

            # If resume_used is not the main resume, we still need to update main resume
            target_resume_for_employment = self.resume_used
            if not self.resume_used.is_main:
                main_resume = Resume.objects.filter(
                    candidate=self.candidate,
                    is_main=True
                ).first()
                if main_resume:
                    target_resume_for_employment = main_resume
        else:
            # No resume_used, find the candidate's main resume
            target_resume_for_employment = Resume.objects.filter(
                candidate=self.candidate,
                is_main=True
            ).first()

            # If no main resume exists, try to find any resume
            if not target_resume_for_employment:
                target_resume_for_employment = Resume.objects.filter(
                    candidate=self.candidate
                ).first()

        # Update employment tracking fields on the target resume
        if target_resume_for_employment:
            # Update work_status if not already set
            target_resume_for_employment.work_status = WorkStatus.EMPLOYED

            # Update employment tracking fields from vacancy
            target_resume_for_employment.current_company_name = vacancy.company.name if vacancy.company else None
            target_resume_for_employment.current_company = vacancy.company
            target_resume_for_employment.current_position = vacancy.title
            target_resume_for_employment.employment_start_date = timezone.now().date()

            # Use vacancy's salary_min as a reasonable default for current salary
            if vacancy.salary_min:
                target_resume_for_employment.current_salary = vacancy.salary_min

            # Set salary currency from vacancy
            target_resume_for_employment.salary_currency = vacancy.salary_currency

            target_resume_for_employment.save(update_fields=[
                'work_status',
                'current_company_name',
                'current_company',
                'current_position',
                'employment_start_date',
                'current_salary',
                'salary_currency',
            ])

    @property
    def days_since_application(self) -> int:
        """
        Calculate how many days ago this application was submitted.
        Useful for reporting and analytics.
        """
        return (timezone.now().date() - self.applied_at.date()).days

    @property
    def is_recent(self) -> bool:
        """
        Determine if this application is considered "recent" (within 30 days).
        """
        return self.days_since_application <= 30

    def can_be_withdrawn(self):
        """
        Business logic: determine if a candidate can still withdraw this application.

        Per spec, candidates can withdraw from APPLIED status, and also from
        AI_FAILED (AI Rejected) — withdrawal is a candidate-only transition
        out of an AI-rejected application, alongside the recruiter's ability
        to route it back into the normal pipeline (see _validate_flexible_transition).
        """
        from apps.applications.models import ApplicationStatusModel, StatusCategory

        try:
            status_model = ApplicationStatusModel.objects.filter(
                company=self.vacancy.company,
                key=self.status,
                is_active=True,
            ).select_related('category').first()
            if status_model:
                return status_model.category.key in (
                    StatusCategory.APPLIED,
                    StatusCategory.AI_FAILED,
                )
        except Exception as e:
            logger.debug(
                "Using legacy can_be_withdrawn logic for application %s: %s",
                self.id, e,
            )

        # Fall back to legacy behavior (APPLIED or AI_FAILED)
        return self.status in (ApplicationStatus.APPLIED, ApplicationStatus.AI_FAILED)

    def can_be_reapplied(self):
        """
        Business logic: determine if a candidate can reapply to this vacancy.

        Reapply is only possible from a WITHDRAWN-category status.
        """
        from apps.applications.models import ApplicationStatusModel, StatusCategory

        try:
            status_model = ApplicationStatusModel.objects.filter(
                company=self.vacancy.company,
                key=self.status,
                is_active=True,
            ).select_related('category').first()
            if status_model:
                return status_model.category.key == StatusCategory.WITHDRAWN
        except Exception as e:
            logger.debug(
                "Using legacy can_be_reapplied logic for application %s: %s",
                self.id, e,
            )

        # Fall back to legacy behavior
        return self.status == ApplicationStatus.WITHDRAWN

    def validate_status_transition(self, new_status, user_type="recruiter"):
        """
        Validate if a status transition is allowed based on current status and user type.
        
        This method supports both the legacy string-based status system and the new
        flexible ApplicationStatusModel system. It first tries the new system, then
        falls back to the legacy hardcoded rules if needed.

        Args:
            new_status: The target status (can be a string key or ApplicationStatusModel)
            user_type: 'candidate' or 'recruiter'

        Returns:
            bool: True if transition is allowed

        Raises:
            ValidationError: If transition is not allowed
        """
        from apps.applications.models import ApplicationStatusModel
        
        # Get the company for this application
        company = self.vacancy.company
        
        # Try to resolve statuses using the new flexible system
        try:
            # Get current status as ApplicationStatusModel
            current_status_model = ApplicationStatusModel.objects.filter(
                company=company,
                key=self.status,
                is_active=True,
            ).select_related('category').first()
            
            # Get target status as ApplicationStatusModel
            if isinstance(new_status, ApplicationStatusModel):
                target_status_model = new_status
            else:
                target_status_model = ApplicationStatusModel.objects.filter(
                    company=company,
                    key=new_status,
                    is_active=True,
                ).select_related('category').first()
            
            # If both statuses exist in the flexible system, use it for validation
            if current_status_model and target_status_model:
                return self._validate_flexible_transition(
                    current_status_model, target_status_model, user_type
                )
        except Exception as exc:
            # Log the exception and fall back to legacy validation if anything goes wrong
            logger.debug(
                "Failed to validate application status transition via flexible system "
                "for application %s (company=%s, current_status=%s, new_status=%s, user_type=%s): %s",
                getattr(self, "id", None),
                getattr(company, "id", None),
                self.status,
                new_status,
                user_type,
                exc,
                exc_info=True,
            )
        
        # Fall back to legacy hardcoded rules
        return self._validate_legacy_transition(new_status, user_type)

    def _validate_flexible_transition(self, current_status, target_status, user_type):
        """
        Validate transition using category-based rules.

        Rules
        -----
        - Same status → always rejected.
        - Recruiter cannot touch WITHDRAWN applications.
        - Cannot REJECT from a terminal status (HIRED, OFFER_REJECTED, REJECTED, WITHDRAWN).
        - Recruiters can move to any status from any non-WITHDRAWN source
          (including rollback from terminal), except that from AI_FAILED they
          cannot set a candidate-decided outcome (WITHDRAWN, HIRED/OFFER_ACCEPTED,
          OFFER_REJECTED) — those remain candidate-only, same as everywhere else.
        - Candidates can only reach a WITHDRAWN-category status via this path
          (withdraw action). All other candidate actions have dedicated endpoints.

        Args:
            current_status: Current ApplicationStatusModel
            target_status: Target ApplicationStatusModel
            user_type: 'candidate' or 'recruiter'

        Returns:
            bool: True if allowed

        Raises:
            ValidationError: If not allowed
        """
        from apps.applications.models import StatusCategory

        if current_status.id == target_status.id:
            raise ValidationError(
                _("Application is already in status '{status}'.").format(
                    status=current_status.label
                )
            )

        if user_type == 'candidate':
            # Candidates can only withdraw (move to a WITHDRAWN-category status)
            if target_status.category.key != StatusCategory.WITHDRAWN:
                raise ValidationError(
                    _("Candidates can only withdraw an application, not change it to '{target}'.").format(
                        target=target_status.label
                    )
                )
            return True

        # --- Recruiter rules ---

        # HR cannot touch WITHDRAWN applications
        if current_status.category.key == StatusCategory.WITHDRAWN:
            raise ValidationError(
                _("Cannot change status of a withdrawn application. "
                  "Only the candidate can reapply.")
            )

        # Cannot move to AI_FAILED — this status is set only by AI auto-reject
        if target_status.category.key == StatusCategory.AI_FAILED:
            raise ValidationError(
                _("Cannot manually move to '{target}' — this status is set only by AI evaluation.").format(
                    target=target_status.label
                )
            )

        # From AI_FAILED, recruiters can move to any status except a
        # candidate-decided outcome (withdraw, offer accepted, offer rejected)
        candidate_only_categories = (
            StatusCategory.WITHDRAWN,
            StatusCategory.HIRED,
            StatusCategory.OFFER_REJECTED,
        )
        if (current_status.category.key == StatusCategory.AI_FAILED
                and target_status.category.key in candidate_only_categories):
            raise ValidationError(
                _("Cannot manually move from '{current}' to '{target}' — "
                  "this transition can only be made by the candidate.").format(
                    current=current_status.label,
                    target=target_status.label,
                )
            )

        # Cannot REJECT from a terminal status
        if (target_status.category.key == StatusCategory.REJECTED
                and current_status.category.is_terminal):
            raise ValidationError(
                _("Cannot reject from '{current}' — this is a terminal status.").format(
                    current=current_status.label
                )
            )

        # Recruiters: all other moves are allowed (warnings via validate-transition API)
        return True
    
    def _validate_legacy_transition(self, new_status, user_type):
        """
        Legacy validation using hardcoded transition rules.
        
        This method is kept for backward compatibility and as a fallback
        when the flexible status system is not initialized.
        """
        from django.utils.translation import gettext as _
        
        current_status = self.status

        # Define allowed transitions for each status and user type
        allowed_transitions = {
            ApplicationStatus.APPLIED: {
                "candidate": [ApplicationStatus.WITHDRAWN],
                "recruiter": [
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.INTERVIEW_SCHEDULED,
                    ApplicationStatus.OFFERED,
                ],
            },
            ApplicationStatus.WITHDRAWN: {
                "candidate": [ApplicationStatus.APPLIED],
                "recruiter": [],  # Recruiters cannot change withdrawn status
            },
            ApplicationStatus.AI_FAILED: {
                # Candidates can withdraw from an AI-rejected application.
                # Recruiters can move it to any other status except the
                # candidate-decided outcomes (withdrawn, offer accepted/rejected).
                "candidate": [ApplicationStatus.WITHDRAWN],
                "recruiter": [
                    ApplicationStatus.APPLIED,
                    ApplicationStatus.INTERVIEW_SCHEDULED,
                    ApplicationStatus.INTERVIEWED,
                    ApplicationStatus.OFFERED,
                    ApplicationStatus.REJECTED,
                ],
            },
            ApplicationStatus.INTERVIEW_SCHEDULED: {
                "candidate": [],  # Candidates cannot change this status
                "recruiter": [
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.INTERVIEWED,
                    ApplicationStatus.OFFERED,
                ],
            },
            ApplicationStatus.INTERVIEWED: {
                "candidate": [],  # Candidates cannot change this status
                "recruiter": [ApplicationStatus.REJECTED, ApplicationStatus.OFFERED],
            },
            ApplicationStatus.OFFERED: {
                "candidate": [
                    ApplicationStatus.OFFER_ACCEPTED,
                    ApplicationStatus.OFFER_REJECTED,
                ],
                "recruiter": [ApplicationStatus.REJECTED],
            },
            ApplicationStatus.REJECTED: {
                "candidate": [],
                "recruiter": [
                    ApplicationStatus.APPLIED,
                    ApplicationStatus.INTERVIEW_SCHEDULED,
                    ApplicationStatus.INTERVIEWED,
                    ApplicationStatus.OFFERED,
                ],
            },
            ApplicationStatus.OFFER_ACCEPTED: {
                "candidate": [],
                "recruiter": [
                    ApplicationStatus.APPLIED,
                    ApplicationStatus.INTERVIEW_SCHEDULED,
                    ApplicationStatus.INTERVIEWED,
                    ApplicationStatus.OFFERED,
                ],
            },
            ApplicationStatus.OFFER_REJECTED: {
                "candidate": [],
                "recruiter": [
                    ApplicationStatus.APPLIED,
                    ApplicationStatus.INTERVIEW_SCHEDULED,
                    ApplicationStatus.INTERVIEWED,
                    ApplicationStatus.OFFERED,
                ],
            },
        }

        # Get allowed transitions for current status and user type
        allowed_for_status = allowed_transitions.get(current_status, {})
        allowed_for_user = allowed_for_status.get(user_type, [])

        if new_status not in allowed_for_user:
            allowed_statuses_display = (
                [ApplicationStatus(status).label for status in allowed_for_user]
                if allowed_for_user
                else [_("None")]
            )
            raise ValidationError(
                _("{user_type} cannot change status from '{current}' to '{new_status}'. "
                  "Allowed transitions: {allowed}").format(
                    user_type=user_type.title(),
                    current=current_status,
                    new_status=new_status,
                    allowed=', '.join(allowed_statuses_display),
                )
            )

        return True

    def advance_status(
            self, new_status, updated_by_recruiter=None, user_type="recruiter", notes=None
    ):
        """
        Helper method to advance application status with proper tracking and validation.

        This encapsulates the business logic around status changes
        and ensures proper audit trails.

        Args:
            new_status: Target status to change to
            updated_by_recruiter: Recruiter instance (if changed by recruiter)
            user_type: 'candidate' or 'recruiter'
            notes: Optional notes for the change
        """
        # Validate the transition
        self.validate_status_transition(new_status, user_type)

        old_status = self.status
        self.status = new_status

        if updated_by_recruiter:
            self.last_updated_by = updated_by_recruiter

        if notes:
            timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
            status_change_note = f"[{timestamp}] Status changed from {old_status} to {new_status} by {user_type}: {notes}"

            if self.recruiter_notes:
                self.recruiter_notes += f"\n\n{status_change_note}"
            else:
                self.recruiter_notes = status_change_note

        self.save()

    @classmethod
    def _get_hired_status_keys(cls, company_id=None):
        from apps.applications.services.hiring_analytics_service import HiringAnalyticsService
        return HiringAnalyticsService.get_hired_status_keys(company_id)

    @classmethod
    def get_applications_count_for_period(cls, start_date, end_date):
        from apps.applications.services.hiring_analytics_service import HiringAnalyticsService
        return HiringAnalyticsService.get_applications_count_for_period(start_date, end_date)

    @classmethod
    def get_applications_comparison(
            cls, current_start, current_end, previous_start, previous_end
    ):
        from apps.applications.services.hiring_analytics_service import HiringAnalyticsService
        return HiringAnalyticsService.get_applications_comparison(
            current_start, current_end, previous_start, previous_end
        )

    @classmethod
    def get_hires_count_for_period(cls, start_date, end_date, company_id=None):
        from apps.applications.services.hiring_analytics_service import HiringAnalyticsService
        return HiringAnalyticsService.get_hires_count_for_period(start_date, end_date, company_id)

    @classmethod
    def get_hiring_dynamics_data(
            cls, end_date, period_days=30, interval="day", company_id=None
    ):
        from apps.applications.services.hiring_analytics_service import HiringAnalyticsService
        return HiringAnalyticsService.get_hiring_dynamics_data(end_date, period_days, interval, company_id)


class ApplicationDocument(AbstractBaseModel):
    """
    Represents additional documents attached to a job application.

    This model allows candidates to upload multiple documents
    (certificates, portfolios, references) beyond just their resume.
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
    )

    application = models.ForeignKey(
        JobApplication, on_delete=models.CASCADE, related_name="documents"
    )

    document_type = models.CharField(
        max_length=20, choices=ApplicationDocumentTypes.choices, default="OTHER"
    )

    title = models.CharField(
        max_length=200, help_text="Descriptive title for this document",
        blank=True,
    )

    file = models.FileField(
        upload_to="application_documents/", help_text="The uploaded document file"
    )

    file_size = models.PositiveIntegerField(
        help_text="File size in bytes", null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()}) - {self.application}"

    def save(self, *args, **kwargs):
        """
        Auto-populate file size and title from uploaded file when saving.
        """
        if self.file:
            if hasattr(self.file, "size"):
                self.file_size = self.file.size
            if not self.title and hasattr(self.file, "name"):
                self.title = os.path.basename(self.file.name)
        super().save(*args, **kwargs)
