"""
Status management service for the flexible application status system.

This module provides:
- Company status initialization from templates
- Status CRUD operations with business rules
- Safe archive with optional batch-move of existing applications

Note: Status *transition validation* lives on the JobApplication model
(``_validate_flexible_transition`` / ``validate_status_transition``) and does
not need a separate service class.
"""

from typing import Optional
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from apps.applications.models import (
    ApplicationStatus,
    StatusCategory,
    ApplicationStatusModel,
    StatusTemplate,
)




class CompanyStatusService:
    """
    Service for managing company-specific statuses.
    
    Provides:
    - Status initialization from templates
    - CRUD operations for custom statuses
    """

    PROTECTED_STATUS_KEYS = {
        ApplicationStatus.APPLIED,
        ApplicationStatus.REJECTED,
    }
    
    def __init__(self, company):
        """
        Initialize the service with a company instance.
        
        Args:
            company: Company instance
        """
        self.company = company
    
    def get_statuses(
        self,
        include_inactive: bool = False,
    ) -> models.QuerySet[ApplicationStatusModel]:
        """
        Get all statuses for the company.
        
        Args:
            include_inactive: If True, include archived statuses
            
        Returns:
            QuerySet of ApplicationStatusModel
        """
        qs = ApplicationStatusModel.objects.filter(
            company=self.company
        ).select_related('category').order_by('position')
        
        if not include_inactive:
            qs = qs.filter(is_active=True)
        
        return qs
    
    def get_kanban_statuses(self) -> models.QuerySet[ApplicationStatusModel]:
        """
        Get statuses visible in Kanban board.
        
        Returns:
            QuerySet of ApplicationStatusModel with show_in_kanban=True
        """
        return self.get_statuses().filter(show_in_kanban=True)
    
    def get_status_by_key(self, key: str) -> Optional[ApplicationStatusModel]:
        """
        Get a status by its key.
        
        Args:
            key: Status key (e.g., 'APPLIED', 'INTERVIEW_SCHEDULED')
            
        Returns:
            ApplicationStatusModel or None
        """
        return ApplicationStatusModel.objects.filter(
            company=self.company,
            key=key.upper(),
            is_active=True,
        ).select_related('category').first()
    
    def get_status_by_category(self, category_key: str) -> models.QuerySet[ApplicationStatusModel]:
        """
        Get all statuses in a specific analytics category.
        
        Args:
            category_key: Category key (e.g., 'HIRED', 'SCREENING')
            
        Returns:
            List of ApplicationStatusModel in that category
        """
        return ApplicationStatusModel.objects.filter(
            company=self.company,
            category__key=category_key,
            is_active=True,
        ).select_related('category').order_by('position')
    
    def get_hired_statuses(self) -> models.QuerySet[ApplicationStatusModel]:
        """Get all statuses that represent 'hired' (for analytics)."""
        return self.get_status_by_category(StatusCategory.HIRED)
    
    @transaction.atomic
    def initialize_from_template(
        self,
        template: Optional[StatusTemplate] = None
    ) -> dict:
        """
        Initialize company statuses from a template.
        
        Args:
            template: StatusTemplate to use. If None, uses default template.
            
        Returns:
            Dictionary with counts of created statuses and rules
            
        Raises:
            ValidationError: If company already has statuses
        """
        # Check if company already has statuses
        if ApplicationStatusModel.objects.filter(company=self.company).exists():
            raise ValidationError(
                _("Company already has statuses initialized. "
                  "Use reset_statuses() first if you want to reinitialize.")
            )
        
        # Get template
        if template is None:
            template = StatusTemplate.objects.filter(is_default=True).first()
            if not template:
                raise ValidationError(_("No default template found."))
        
        # Use template's apply method
        return template.apply_to_company(self.company)

    @transaction.atomic
    def create_status(
        self,
        key: str,
        label: str,
        category: 'StatusCategory',
        color: str = '#6B7280',
        position: Optional[int] = None,
        show_in_kanban: bool = True,
        translations: Optional[dict] = None,
    ) -> ApplicationStatusModel:
        """
        Create a new company status.

        Business rule: single-column categories cannot have more than one
        active ApplicationStatusModel per company.

        Raises:
            ValidationError: If the category is single-column and a status
                already exists for this company + category.
        """
        if category.is_single_column:
            existing = ApplicationStatusModel.objects.filter(
                company=self.company,
                category=category,
                is_active=True,
            ).exists()
            if existing:
                raise ValidationError(
                    _("Category '{category}' only allows one status column. "
                      "A status already exists for this category.").format(
                        category=category.label
                    )
                )

        if position is None:
            max_pos = ApplicationStatusModel.objects.filter(
                company=self.company,
            ).aggregate(max_pos=models.Max('position'))['max_pos']
            position = (max_pos or 0) + 1

        return ApplicationStatusModel.objects.create(
            key=key.upper(),
            label=label,
            company=self.company,
            category=category,
            color=color,
            position=position,
            show_in_kanban=show_in_kanban,
            translations=translations or {},
            is_default=False,
            is_active=True,
        )

    @transaction.atomic
    def archive_status(
        self,
        status: ApplicationStatusModel,
        move_to_status: Optional[ApplicationStatusModel] = None,
    ) -> dict:
        """
        Archive a status (soft delete), optionally relocating its applications.

        Business rules
        --------------
        - If `move_to_status` is provided, all active applications currently in
          `status` are atomically moved to `move_to_status` before archiving.
        - If `move_to_status` is **not** provided and there are active
          applications in `status`, a ``ValidationError`` is raised with an
          ``applications_count`` attribute so the caller can return HTTP 409.

        Returns:
            ``{'archived': True, 'applications_moved': int}``

        Raises:
            ValidationError: If the status doesn't belong to this company, or
                it has applications and no move target was given.
        """
        from apps.applications.models import JobApplication

        if status.company_id != self.company.id:
            raise ValidationError(_("Status does not belong to this company."))

        if status.key in self.PROTECTED_STATUS_KEYS:
            raise ValidationError(
                _("Cannot archive protected status '{label}'.").format(
                    label=status.label
                )
            )

        applications = JobApplication.objects.filter(
            vacancy__company=self.company,
            status=status.key,
            is_active=True,
        )
        count = applications.count()

        if count > 0:
            if move_to_status is None:
                err = ValidationError(
                    _(
                        "Cannot archive status '{label}' — it has {count} active "
                        "application(s). Provide move_to_status_id to relocate them."
                    ).format(label=status.label, count=count)
                )
                err.applications_count = count
                raise err

            if move_to_status.company_id != self.company.id:
                raise ValidationError(
                    _("Target status does not belong to this company.")
                )
            if move_to_status.id == status.id:
                raise ValidationError(
                    _("Cannot move applications to the same status being archived.")
                )

            applications.update(status=move_to_status.key)

        status.is_active = False
        status.save(update_fields=["is_active", "updated_at"])

        return {"archived": True, "applications_moved": count}
