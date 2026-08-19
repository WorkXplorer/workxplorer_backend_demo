"""
v2 application serializers.

The primary difference from v1: the `status` field is returned as a rich
object `{id, key, label, localized_label, color, category_key}` rather than
a plain string, enabling the frontend to render Kanban columns with colours
and localised labels without extra API calls.

The update serializer accepts `status_id` (UUID of ApplicationStatusModel)
instead of a plain status string.
"""
import logging

from rest_framework import serializers
from django.utils.translation import gettext as _

from apps.applications.models import ApplicationStatusModel
from apps.applications.serializers.application import (
    JobApplicationListSerializer,
    JobApplicationDetailSerializer,
)
from utils.language import get_request_language

logger = logging.getLogger(__name__)


class JobApplicationV2ListSerializer(JobApplicationListSerializer):
    """
    v2 list serializer — adds rich status object alongside the plain string.

    Fields changed vs v1:
    - `status_info`: full status object (id, key, label, color, category_key)
    """

    status_info = serializers.SerializerMethodField()

    class Meta(JobApplicationListSerializer.Meta):
        fields = JobApplicationListSerializer.Meta.fields + ["status_info"]

    def get_status_info(self, obj):
        """Resolve the application status to its ApplicationStatusModel data."""
        try:
            company = obj.vacancy.company
            status_model = ApplicationStatusModel.objects.filter(
                company=company,
                key=obj.status,
                is_active=True,
            ).select_related("category").first()
            if status_model:
                language = get_request_language()
                return {
                    "id": str(status_model.id),
                    "key": status_model.key,
                    "label": status_model.label,
                    "localized_label": status_model.get_localized_label(language),
                    "color": status_model.color,
                    "category_key": status_model.category.key,
                    "is_terminal": status_model.category.is_terminal,
                }
        except Exception:
            logger.exception(
                "Failed to resolve status_info in JobApplicationV2ListSerializer for application_id=%s",
                getattr(obj, "id", None),
            )
        return None


class JobApplicationV2DetailSerializer(JobApplicationDetailSerializer):
    """
    v2 detail serializer — adds rich status object.
    """

    status_info = serializers.SerializerMethodField()

    class Meta(JobApplicationDetailSerializer.Meta):
        fields = JobApplicationDetailSerializer.Meta.fields + ["status_info"]

    def get_status_info(self, obj):
        """Resolve the application status to its ApplicationStatusModel data."""
        try:
            company = obj.vacancy.company
            status_model = ApplicationStatusModel.objects.filter(
                company=company,
                key=obj.status,
                is_active=True,
            ).select_related("category").first()
            if status_model:
                language = get_request_language()
                return {
                    "id": str(status_model.id),
                    "key": status_model.key,
                    "label": status_model.label,
                    "localized_label": status_model.get_localized_label(language),
                    "color": status_model.color,
                    "category_key": status_model.category.key,
                    "is_terminal": status_model.category.is_terminal,
                }
        except Exception:
            logger.exception(
                "Failed to resolve status_info in JobApplicationV2DetailSerializer for application_id=%s",
                getattr(obj, "id", None),
            )
        return None


class JobApplicationV2UpdateSerializer(serializers.Serializer):
    """
    v2 update serializer for recruiter status changes.

    Accepts `status_id` (UUID of ApplicationStatusModel) instead of a
    plain status string.  All other fields (kanban_position, recruiter_notes,
    etc.) are passed through as-is.
    """

    status_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=_("UUID of the target ApplicationStatusModel."),
    )
    kanban_position = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    recruiter_notes = serializers.CharField(required=False, allow_blank=True)
    earliest_start_date = serializers.DateField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True)

    def validate_status_id(self, value):
        if value is None:
            return value
        company = self.context.get("company")
        try:
            status_model = ApplicationStatusModel.objects.select_related("category").get(
                id=value,
                is_active=True,
            )
        except ApplicationStatusModel.DoesNotExist:
            raise serializers.ValidationError(_("Status not found."))
        if company and status_model.company_id != company.id:
            raise serializers.ValidationError(
                _("Status does not belong to your company.")
            )
        # Store resolved model for view consumption
        self._resolved_status = status_model
        return value

    @property
    def resolved_status(self):
        """Return the resolved ApplicationStatusModel after validate_status_id."""
        return getattr(self, "_resolved_status", None)

    def create(self, validated_data):
        """This serializer is update-only and should not be used for creation."""
        raise NotImplementedError("JobApplicationV2UpdateSerializer does not support create().")

    # ponytail: no update() needed — view overrides perform_update() and handles persistence.
