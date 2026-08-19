import logging
import uuid as uuid_lib

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, OpenApiResponse

from core.responses import APIResponse
from utils.view_mixins import RecruiterMixin

from apps.applications.models import ApplicationStatusModel, JobApplication, StatusCategory
from apps.conversations.services import create_status_change_message
from apps.notifications.services import ApplicationNotificationService

logger = logging.getLogger(__name__)

MAX_REVALUATION_IDS = 100


class AIRevaluationView(RecruiterMixin, APIView):
    """
    POST /api/v2/applications/ai-revaluation/

    Move applications from AI_FAILED status back to APPLIED or to REJECTED.

    Request body:
        application_ids (list[uuid]): List of application UUIDs (max 100)
        reject (bool): If true, move to REJECTED. If false (default), move to APPLIED.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai_revaluation"

    def _validate_application_ids(self, raw_ids: list) -> list[uuid_lib.UUID]:
        valid = []
        errors = []
        for idx, val in enumerate(raw_ids):
            try:
                valid.append(uuid_lib.UUID(str(val)))
            except (ValueError, AttributeError):
                errors.append({"index": idx, "value": val, "error": _("Invalid UUID format.")})
        if errors:
            raise ValidationError({"application_ids": errors})
        return valid

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "application_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "description": "List of application UUIDs (max 100)",
                    },
                    "reject": {
                        "type": "boolean",
                        "description": "If true, move to REJECTED. If false (default), move to APPLIED.",
                    },
                },
                "required": ["application_ids"],
                "example": {
                    "application_ids": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
                    "reject": False,
                },
            }
        },
        responses={
            200: OpenApiResponse(
                description="Applications successfully revaluated",
                response={
                    "type": "object",
                    "properties": {
                        "updated_count": {
                            "type": "integer",
                            "description": "Number of applications updated",
                        },
                        "target_status": {
                            "type": "string",
                            "description": "Target status key (applied/rejected)",
                        },
                    },
                },
            ),
            400: OpenApiResponse(description="Validation error - invalid UUID, missing fields, or status not configured"),
            401: OpenApiResponse(description="Unauthorized"),
        },
        tags=["Applications", "AI Revaluation"],
        summary="Move applications from AI_FAILED to APPLIED or REJECTED",
        description=(
            "Moves a batch of applications from AI_FAILED status back to APPLIED (default) "
            "or to REJECTED. Validates that all application IDs belong to the recruiter's "
            "company and are currently in AI_FAILED status. Creates audit trail messages "
            "and sends candidate notifications."
        ),
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        recruiter = self.get_recruiter()
        company = recruiter.company

        raw_ids = request.data.get("application_ids", [])
        reject = request.data.get("reject", False)

        if not isinstance(raw_ids, list) or not raw_ids:
            raise ValidationError(
                {"application_ids": _("A non-empty list of application IDs is required.")}
            )

        if len(raw_ids) > MAX_REVALUATION_IDS:
            raise ValidationError(
                _("A maximum of {max} applications can be revalued at once.").format(
                    max=MAX_REVALUATION_IDS
                )
            )

        if not isinstance(reject, bool):
            raise ValidationError({"reject": _("Must be a boolean value.")})

        application_ids = self._validate_application_ids(raw_ids)

        # Fetch company's relevant statuses
        ai_failed_status = ApplicationStatusModel.objects.filter(
            company=company,
            category__key=StatusCategory.AI_FAILED,
            is_active=True,
        ).first()

        if not ai_failed_status:
            raise ValidationError(_("AI Failed status is not configured for this company."))

        target_category = StatusCategory.APPLIED if not reject else StatusCategory.REJECTED
        target_status = ApplicationStatusModel.objects.filter(
            company=company,
            category__key=target_category,
            is_active=True,
        ).first()

        if not target_status:
            raise ValidationError(
                _("Target status '{status}' is not configured for this company.").format(
                    status=target_category
                )
            )

        # Fetch applications belonging to this company and currently in AI_FAILED status
        applications = JobApplication.objects.filter(
            id__in=application_ids,
            vacancy__company=company,
            status=ai_failed_status.key,
        ).select_for_update()

        found_ids = set(str(a.id) for a in applications)
        requested_ids = set(str(uid) for uid in application_ids)

        not_found = requested_ids - found_ids
        if not_found:
            raise ValidationError(
                _("One or more applications were not found or are not in AI_FAILED status.")
            )

        # Perform the status update with audit trail
        now = timezone.now()
        updated_count = 0
        for application in applications:
            old_status = application.status
            application._cached_old_status = old_status
            application._cached_is_hired = False
            application.status = target_status.key
            application.updated_at = now
            application.last_updated_by = recruiter
            application.save(
                update_fields=["status", "updated_at", "in_review_at", "hired_at", "last_updated_by"],
                skip_full_clean=True,
            )

            # Create conversation message for audit trail
            try:
                create_status_change_message(
                    application=application,
                    old_status=old_status,
                    new_status=target_status.key,
                    recruiter_note=None,
                    changed_by="RECRUITER",
                )
            except Exception as e:
                logger.warning(
                    f"[AIRevaluation] Failed to create status change message for "
                    f"application {application.id}: {e}"
                )

            # Send notification to candidate
            try:
                ApplicationNotificationService.notify_candidate_status_updated(
                    application,
                    old_status=old_status,
                    new_status=target_status.key,
                )
            except Exception as e:
                logger.warning(
                    f"[AIRevaluation] Failed to send notification for "
                    f"application {application.id}: {e}"
                )

            updated_count += 1

        return APIResponse.success(
            data={
                "updated_count": updated_count,
                "target_status": target_status.key,
            },
            message=_("{count} application(s) moved to {status}.").format(
                count=updated_count,
                status=target_status.label,
            ),
            status_code=status.HTTP_200_OK,
        )


ai_revaluation_view = AIRevaluationView.as_view()
