"""
v2 recruiter application views.

Primary change from v1: ``UpdateApplicationStatusV2View`` accepts
``status_id`` (UUID of ApplicationStatusModel) instead of a plain
TextChoices string.  All Kanban reordering logic is preserved by
resolving the UUID to a string key before delegating to the parent.
"""

from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from apps.applications.models import ApplicationStatusModel
from apps.applications.serializers.v2.application import (
    JobApplicationV2UpdateSerializer,
)
from apps.applications.views.recruiter import UpdateApplicationStatusView


class UpdateApplicationStatusV2View(UpdateApplicationStatusView):
    """
    v2 recruiter status-update endpoint.

    Accepts ``status_id`` (UUID) instead of a plain status string.
    The UUID is resolved to the corresponding ``ApplicationStatusModel``
    and its ``key`` is injected into ``validated_data["status"]`` so that
    the parent ``perform_update`` can work unchanged.
    """

    serializer_class = JobApplicationV2UpdateSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        try:
            recruiter = self.get_recruiter()
            context["company"] = recruiter.company
        except (AttributeError, ValidationError):
            context["company"] = None
        return context

    @transaction.atomic
    def perform_update(self, serializer):
        """
        Resolve status_id to a status key, then delegate to parent perform_update.
        """
        status_id = serializer.validated_data.get("status_id")

        if status_id:
            resolved_status = getattr(serializer, "_resolved_status", None)
            if resolved_status is None:
                try:
                    resolved_status = ApplicationStatusModel.objects.get(id=status_id)
                except ApplicationStatusModel.DoesNotExist:
                    raise ValidationError({"status_id": _("Status not found.")})

            serializer.validated_data["status"] = resolved_status.key

        super().perform_update(serializer)


update_application_status_view = UpdateApplicationStatusV2View.as_view()
