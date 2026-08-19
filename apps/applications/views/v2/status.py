"""
v2 status management views.

All status management views live here — v2 only.
Includes:
- Status categories (read-only analytics grouping)
- Company status CRUD (list, create, update, archive, reorder)

V2-specific features:
- Enhanced archive endpoint (batch-move + HTTP 409 with count)
- Auto-key generation on status creation (via v2 serializer)
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from core.responses import APIResponse
from utils.view_mixins import RecruiterMixin
from utils import IsRecruiterPermission, IsAdminRecruiter

from apps.applications.models import (
    StatusCategory,
    ApplicationStatusModel,
)
from apps.applications.serializers import (
    StatusCategorySerializer,
    ApplicationStatusSerializer,
    StatusReorderSerializer,
)
from apps.applications.serializers.v2.status import (
    ApplicationStatusV2Serializer,
    ArchiveStatusV2Serializer,
)
from apps.applications.services import CompanyStatusService


logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Application Statuses'],
    description="List all analytics categories (system-defined, read-only)"
)
class StatusCategoryListView(generics.ListAPIView):
    """
    List all status categories for analytics.
    
    Categories are system-defined and cannot be modified.
    They provide the analytics grouping for custom statuses.
    """
    
    serializer_class = StatusCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    
    def get_queryset(self):
        return StatusCategory.objects.all().order_by('position')


@extend_schema(
    tags=['Application Statuses'],
    description="List all application statuses for the recruiter's company"
)
class CompanyStatusListView(RecruiterMixin, generics.ListAPIView):
    """
    List all statuses for the recruiter's company.
    
    Returns statuses in position order, suitable for:
    - Kanban board column headers
    - Status selection dropdowns
    - Status management UI
    """
    
    serializer_class = ApplicationStatusSerializer
    permission_classes = [IsRecruiterPermission]
    pagination_class = None
    
    def get_queryset(self):
        recruiter = self.get_recruiter()
        include_inactive = self.request.query_params.get('include_inactive', 'false').lower() == 'true'
        
        service = CompanyStatusService(recruiter.company)
        return service.get_statuses(include_inactive=include_inactive)


@extend_schema(
    tags=["Application Statuses"],
    description=(
        "Create a new custom status for the company. "
        "The `key` field is optional — it is auto-generated from `label` when omitted."
    ),
)
class CompanyStatusCreateV2View(RecruiterMixin, APIView):
    """
    Create a custom status.

    If `key` is omitted the backend derives it from `label`:
      "Tech Interview" → "TECH_INTERVIEW" (collision suffix appended if needed).
    """

    permission_classes = [IsAdminRecruiter]

    def get_serializer_context(self):
        recruiter = self.get_recruiter()
        return {
            "request": self.request,
            "company": recruiter.company,
        }

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        recruiter = self.get_recruiter()
        serializer = ApplicationStatusV2Serializer(
            data=request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        status = serializer.save(company=recruiter.company, is_default=False)

        data = ApplicationStatusV2Serializer(
            status, context=self.get_serializer_context()
        ).data

        return APIResponse.created(
            data=data,
            message=_("Status '{label}' created successfully.").format(
                label=status.label
            ),
        )


@extend_schema(
    tags=['Application Statuses'],
    description="Update a custom status"
)
class CompanyStatusUpdateView(RecruiterMixin, generics.UpdateAPIView):
    """
    Update an existing status.
    
    Can update:
    - label: Display name
    - color: Hex color
    - position: Display order
    - translations: Localized labels
    - show_in_kanban: Kanban visibility
    
    Cannot update:
    - key: Status key (immutable)
    - category: Analytics category (immutable after creation)
    """
    
    serializer_class = ApplicationStatusSerializer
    permission_classes = [IsAdminRecruiter]
    lookup_field = 'id'
    lookup_url_kwarg = 'status_id'
    
    def get_queryset(self):
        recruiter = self.get_recruiter()
        return ApplicationStatusModel.objects.filter(
            company=recruiter.company,
            is_active=True,
        )
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return APIResponse.success(
            data=serializer.data,
            message=_("Status updated successfully.")
        )


@extend_schema(
    tags=["Application Statuses"],
    description=(
        "Archive a status (soft-delete). "
        "If the status has active applications and `move_to_status_id` is "
        "provided, all applications are batch-moved before archiving. "
        "If the status has applications and `move_to_status_id` is omitted, "
        "HTTP 409 is returned with the number of affected applications."
    ),
)
class CompanyStatusArchiveV2View(RecruiterMixin, APIView):
    """
    Archive a status with optional batch-move of existing applications.

    Request body (optional):
    - ``move_to_status_id``: UUID of target status for existing applications.

    Responses:
    - 200 — archived (with ``applications_moved`` count)
    - 409 — has applications and no move target given
    """

    permission_classes = [IsAdminRecruiter]

    def post(self, request, status_id, *args, **kwargs):
        recruiter = self.get_recruiter()

        try:
            status = ApplicationStatusModel.objects.get(
                id=status_id,
                company=recruiter.company,
                is_active=True,
            )
        except ApplicationStatusModel.DoesNotExist:
            return APIResponse.not_found(message=_("Status not found."))

        serializer = ArchiveStatusV2Serializer(
            data=request.data,
            context={"company": recruiter.company},
        )
        serializer.is_valid(raise_exception=True)

        move_to_id = serializer.validated_data.get("move_to_status_id")
        move_to_status = None
        if move_to_id:
            try:
                move_to_status = ApplicationStatusModel.objects.get(
                    id=move_to_id,
                    company=recruiter.company,
                    is_active=True,
                )
            except ApplicationStatusModel.DoesNotExist:
                return APIResponse.not_found(message=_("Target status not found."))

        service = CompanyStatusService(recruiter.company)

        try:
            result = service.archive_status(status, move_to_status=move_to_status)
            return APIResponse.success(
                data=result,
                message=_("Status '{label}' archived.").format(label=status.label),
            )
        except ValidationError as exc:
            count = getattr(exc, "applications_count", None)
            if count is not None:
                return APIResponse.conflict(
                    message=str(exc.messages[0]),
                    details={"applications_count": count},
                )
            return APIResponse.validation_error(
                field_errors=exc.message_dict if hasattr(exc, "message_dict") else None,
                details=None if hasattr(exc, "message_dict") else {"detail": exc.messages},
            )
        except Exception:
            logger.exception(
                "Unexpected error archiving status '%s' for company '%s'.",
                status_id,
                recruiter.company.id,
            )
            return APIResponse.server_error(
                message=_("An unexpected error occurred while archiving the status.")
            )


@extend_schema(
    tags=['Application Statuses'],
    description="Reorder statuses for kanban display"
)
class CompanyStatusReorderView(RecruiterMixin, APIView):
    """
    Bulk reorder statuses.
    
    Accepts a list of status IDs in the desired order.
    Updates the position field for each status.
    """
    
    permission_classes = [IsAdminRecruiter]
    
    def patch(self, request, *args, **kwargs):
        recruiter = self.get_recruiter()
        
        serializer = StatusReorderSerializer(
            data=request.data,
            context={'company': recruiter.company}
        )
        serializer.is_valid(raise_exception=True)
        
        count = serializer.save()
        
        return APIResponse.success(
            message=_("{count} statuses reordered successfully.").format(count=count)
        )


# View function aliases
status_category_list_view = StatusCategoryListView.as_view()
company_status_list_view = CompanyStatusListView.as_view()
company_status_create_view = CompanyStatusCreateV2View.as_view()
company_status_update_view = CompanyStatusUpdateView.as_view()
company_status_archive_view = CompanyStatusArchiveV2View.as_view()
company_status_reorder_view = CompanyStatusReorderView.as_view()
