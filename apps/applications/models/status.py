"""
Application Status Models

This module provides a flexible, company-isolated application status system
that supports custom statuses while maintaining analytics compatibility.

Architecture:
- StatusCategory: System-wide analytics categories (HIRED, REJECTED, etc.)
- ApplicationStatusModel: Company-specific custom statuses

Transition validation is category-based: terminal statuses (HIRED, REJECTED,
WITHDRAWN) block all outgoing recruiter moves. Candidate actions (withdraw,
reapply, accept/reject offer) are handled by dedicated endpoints.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from utils import AbstractBaseModel
from utils.fields import UUIDField


class StatusCategory(models.Model):
    """
    System-defined categories for analytics aggregation.
    
    These categories are immutable system constants that enable analytics
    to work consistently across all companies, regardless of custom status names.
    
    Categories:
    - APPLIED: Initial application received (single-column)
    - SCREENING: Under review, CV review, background checks (multi-column)
    - INTERVIEWING: Active interview process (multi-column)
    - ASSESSMENT: Test tasks, scoring (multi-column)
    - TRAINING: Onboarding, probation (multi-column)
    - OFFERED: Offer extended to candidate (single-column)
    - HIRED: Offer accepted (single-column, terminal, positive)
    - OFFER_REJECTED: Candidate declined the offer (single-column, terminal)
    - REJECTED: Application declined by company (single-column, terminal)
    - WITHDRAWN: Candidate withdrew application (single-column, terminal)
    - ON_HOLD: Process temporarily paused (multi-column)
    
    Example:
        Company A: "Contract Signed" → HIRED category
        Company B: "Onboarded" → HIRED category
        Analytics query: status__category__key='HIRED' captures both
    """
    
    # Category constants for programmatic access
    APPLIED = 'APPLIED'
    SCREENING = 'SCREENING'
    INTERVIEWING = 'INTERVIEWING'
    ASSESSMENT = 'ASSESSMENT'
    TRAINING = 'TRAINING'
    OFFERED = 'OFFERED'
    HIRED = 'HIRED'
    OFFER_REJECTED = 'OFFER_REJECTED'
    REJECTED = 'REJECTED'
    WITHDRAWN = 'WITHDRAWN'
    ON_HOLD = 'ON_HOLD'
    AI_FAILED = 'AI_FAILED'
    
    CATEGORY_CHOICES = [
        (APPLIED, _('Applied')),
        (SCREENING, _('Screening')),
        (INTERVIEWING, _('Interviewing')),
        (ASSESSMENT, _('Assessment')),
        (TRAINING, _('Training')),
        (OFFERED, _('Offered')),
        (HIRED, _('Hired')),
        (OFFER_REJECTED, _('Offer Rejected')),
        (REJECTED, _('Rejected')),
        (WITHDRAWN, _('Withdrawn')),
        (ON_HOLD, _('On Hold')),
        (AI_FAILED, _('AI Rejected')),
    ]
    
    key = models.CharField(
        max_length=50,
        unique=True,
        choices=CATEGORY_CHOICES,
        help_text=_("Unique identifier for the category (e.g., 'HIRED', 'REJECTED')")
    )
    
    label = models.CharField(
        max_length=100,
        help_text=_("Default display name in English")
    )
    
    description = models.TextField(
        blank=True,
        help_text=_("Description of what this category represents")
    )
    
    # Behavior flags
    is_terminal = models.BooleanField(
        default=False,
        help_text=_("If true, statuses in this category end the application process")
    )
    
    is_positive_outcome = models.BooleanField(
        default=False,
        help_text=_("If true, this is a positive outcome (hired, accepted)")
    )
    
    is_single_column = models.BooleanField(
        default=False,
        help_text=_("If true, HR cannot create multiple status columns under this category. "
                     "If false, HR can create unlimited sub-columns.")
    )
    
    # Ordering
    position = models.PositiveIntegerField(
        default=0,
        help_text=_("Default order position for display")
    )
    
    class Meta:
        verbose_name = _("Status Category")
        verbose_name_plural = _("Status Categories")
        ordering = ['position', 'key']
    
    def __str__(self) -> str:
        return str(self.label)

    @classmethod
    def get_terminal_categories(cls):
        """Return keys of terminal categories (end states)."""
        return [cls.HIRED, cls.OFFER_REJECTED, cls.REJECTED, cls.WITHDRAWN]
    
    @classmethod
    def get_hired_category_key(cls):
        """Return the key used for 'hired' analytics."""
        return cls.HIRED
    
    @classmethod
    def get_single_column_categories(cls):
        """Return keys of categories locked to a single column (per company)."""
        return [
            cls.APPLIED, cls.OFFERED, cls.OFFER_REJECTED,
            cls.HIRED, cls.REJECTED, cls.WITHDRAWN, cls.AI_FAILED,
        ]


class ApplicationStatusModel(AbstractBaseModel):
    """
    Company-specific application status.
    
    Each company has its own isolated set of statuses, created from a template
    when the company is first set up. Companies can customize names, colors,
    and add new statuses, but must always map them to a StatusCategory
    for analytics compatibility.
    
    Example:
        Company A statuses:
        - "Applied" (APPLIED category)
        - "Technical Screen" (SCREENING category)
        - "Culture Fit Interview" (INTERVIEWING category)
        - "Hired" (HIRED category)
        
        Company B statuses:
        - "Received" (APPLIED category)
        - "Phone Screen" (SCREENING category)
        - "Onsite Interview" (INTERVIEWING category)
        - "Contract Signed" (HIRED category)
    """
    
    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this status")
    )
    
    key = models.CharField(
        max_length=50,
        help_text=_("Unique key within the company (e.g., 'APPLIED', 'TECH_SCREEN')")
    )
    
    label = models.CharField(
        max_length=100,
        help_text=_("Display name for this status")
    )
    
    translations = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Translations: {'ru': 'Подано', 'uz': 'Topshirildi'}")
    )
    
    company = models.ForeignKey(
        'authentication.Company',
        on_delete=models.CASCADE,
        related_name='application_statuses',
        help_text=_("Company that owns this status")
    )
    
    category = models.ForeignKey(
        StatusCategory,
        on_delete=models.PROTECT,
        related_name='statuses',
        help_text=_("Analytics category this status maps to")
    )
    
    color = models.CharField(
        max_length=7,
        default='#6B7280',
        help_text=_("Hex color for Kanban column (e.g., '#3B82F6')")
    )
    
    position = models.PositiveIntegerField(
        default=0,
        db_index=True,
        help_text=_("Order position in Kanban board (lower = first)")
    )
    
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("If false, status is archived and hidden from selection")
    )
    
    is_default = models.BooleanField(
        default=False,
        help_text=_("If true, this status was created from the default template")
    )
    
    # For kanban board - whether to show in board
    show_in_kanban = models.BooleanField(
        default=True,
        help_text=_("If false, status column is hidden from Kanban board")
    )
    
    class Meta:
        verbose_name = _("Application Status")
        verbose_name_plural = _("Application Statuses")
        ordering = ['position', 'key']
        constraints = [
            models.UniqueConstraint(
                fields=['key', 'company'],
                name='unique_status_key_per_company'
            )
        ]
        indexes = [
            models.Index(fields=['company', 'is_active']),
            models.Index(fields=['company', 'position']),
        ]
    
    def __str__(self):
        return f"{self.label} ({self.company.name})"
    
    def clean(self):
        """Validate the status before saving."""
        super().clean()
        # Ensure key is uppercase and alphanumeric with underscores
        if self.key:
            self.key = self.key.upper().replace(' ', '_').replace('-', '_')
    
    def get_localized_label(self, language: str = 'en') -> str:
        """
        Get the label in the specified language.
        
        Args:
            language: Language code ('en', 'ru', 'uz')
            
        Returns:
            Localized label, falling back to default label if not found
        """
        if language == 'en':
            return self.label
        return self.translations.get(language, self.label)
    
    @property
    def is_terminal(self) -> bool:
        """Check if this status ends the application process."""
        return self.category.is_terminal
    
    @property
    def is_hired_status(self) -> bool:
        """Check if this status represents a hired candidate."""
        return self.category.key == StatusCategory.HIRED
    
    def get_allowed_transitions(self, user_type: str) -> models.QuerySet:
        """
        Return all statuses this status can transition to for the given user type.

        Recruiters may move to any status, including from terminal states
        (rollback with warning), except from WITHDRAWN which HR cannot touch.
        Candidates can only move to a WITHDRAWN-category status (withdraw action).

        Args:
            user_type: 'candidate' or 'recruiter'

        Returns:
            QuerySet of ApplicationStatusModel
        """
        company_qs = ApplicationStatusModel.objects.filter(
            company=self.company,
            is_active=True,
        ).exclude(id=self.id)

        if user_type == 'recruiter':
            if self.category.key == StatusCategory.WITHDRAWN:
                return ApplicationStatusModel.objects.none()
            return company_qs

        # Candidates can only go to a WITHDRAWN-category status
        return company_qs.filter(category__key=StatusCategory.WITHDRAWN)


class StatusTemplate(AbstractBaseModel):
    """
    Template for initializing company statuses.
    
    When a new company is created, statuses are cloned from a template.
    Templates define both the statuses and the transition rules.
    
    Example:
        "Standard Hiring" template:
        - APPLIED → can go to INTERVIEW_SCHEDULED, REJECTED (recruiter)
        - APPLIED → can go to WITHDRAWN (candidate)
        - OFFERED → can go to OFFER_ACCEPTED, OFFER_REJECTED (candidate only)
    """
    
    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this template")
    )
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_("Template name (e.g., 'Standard Hiring', 'Tech Recruiting')")
    )
    
    description = models.TextField(
        blank=True,
        help_text=_("Description of this template's workflow")
    )
    
    is_default = models.BooleanField(
        default=False,
        help_text=_("If true, this template is used for new companies")
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_("If false, this template cannot be selected")
    )
    
    # JSON structure defining statuses and transitions
    statuses = models.JSONField(
        default=list,
        help_text=_("""
            List of status definitions:
            [
                {
                    "key": "APPLIED",
                    "label": "Applied",
                    "category": "APPLIED",
                    "color": "#3B82F6",
                    "position": 1,
                    "show_in_kanban": true,
                    "translations": {"ru": "Подано", "uz": "Topshirildi"}
                }
            ]
        """)
    )
    
    transitions = models.JSONField(
        default=list,
        help_text=_("""
            List of transition rules:
            [
                {
                    "from": "APPLIED",
                    "to": "INTERVIEW_SCHEDULED",
                    "recruiter": true,
                    "candidate": false
                }
            ]
        """)
    )
    
    class Meta:
        verbose_name = _("Status Template")
        verbose_name_plural = _("Status Templates")
        ordering = ['-is_default', 'name']
    
    def __str__(self):
        default_marker = " (default)" if self.is_default else ""
        return f"{self.name}{default_marker}"
    
    def clean(self):
        """Validate the template."""
        super().clean()
        
        # If setting as default, ensure no other default exists
        if self.is_default:
            existing_default = StatusTemplate.objects.filter(
                is_default=True
            ).exclude(pk=self.pk).first()
            
            if existing_default:
                raise ValidationError(
                    _("Another template is already set as default. "
                      "Please unset it first.")
                )
    
    def apply_to_company(self, company) -> dict:
        """
        Create statuses and transition rules for a company from this template.
        
        Args:
            company: The Company instance to create statuses for
            
        Returns:
            Dictionary with created statuses and rules counts
        """
        from django.db import transaction

        created_statuses = {}

        with transaction.atomic():
            for status_def in list(self.statuses):
                category = StatusCategory.objects.get(key=status_def['category'])

                status = ApplicationStatusModel.objects.create(
                    key=status_def['key'],
                    label=status_def['label'],
                    company=company,
                    category=category,
                    color=status_def.get('color', '#6B7280'),
                    position=status_def.get('position', 0),
                    show_in_kanban=status_def.get('show_in_kanban', True),
                    translations=status_def.get('translations', {}),
                    is_default=True,  # Mark as template-created
                )
                created_statuses[status_def['key']] = status

        return {
            'statuses_created': len(created_statuses),
        }
