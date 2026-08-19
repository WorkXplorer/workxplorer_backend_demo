"""
v2 status serializers.

Extends the v1 status serializers with:
- Auto-key generation from label when `key` is omitted
- Key uniqueness-collision handling (suffix _2, _3, ...)
- `move_to_status_id` field for the archive endpoint
"""

import re

from rest_framework import serializers
from django.utils.translation import gettext as _

from apps.applications.models import (
    ApplicationStatusModel,
)
from apps.applications.serializers.status import (
    ApplicationStatusSerializer,
)


def slugify_status_key(label: str) -> str:
    """
    Convert a human-readable label to an UPPER_SNAKE_CASE status key.

    Examples:
        "Tech Interview"          -> "TECH_INTERVIEW"
        "HR Review (HQ)"          -> "HR_REVIEW_HQ"
        "Background Check — Round 2" -> "BACKGROUND_CHECK_ROUND_2"
    """
    # Normalize unicode (strip accents), uppercase
    normalized = label.upper()
    # Replace anything that is not A-Z, 0-9 with underscore
    key = re.sub(r"[^A-Z0-9]+", "_", normalized)
    # Strip leading/trailing underscores and collapse multiples
    key = re.sub(r"_+", "_", key).strip("_")
    return key


def make_unique_key(base_key: str, company) -> str:
    """
    Return `base_key` if it does not collide with existing company statuses,
    otherwise append _2, _3, … until a free slot is found.
    """
    key = base_key
    counter = 2
    while ApplicationStatusModel.objects.filter(company=company, key=key).exists():
        key = f"{base_key}_{counter}"
        counter += 1
    return key


class ApplicationStatusV2Serializer(ApplicationStatusSerializer):
    """
    v2 status serializer — `key` is optional on creation.

    When `key` is omitted the backend auto-derives it from `label` using
    slugify_status_key() and then ensures uniqueness within the company.

    On update `key` and `category` remain immutable (same as v1).
    """

    key = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=_(
            "Optional unique key (e.g. 'TECH_INTERVIEW'). "
            "Auto-generated from label when omitted."
        ),
    )

    def validate(self, attrs):
        """Auto-generate key from label if not provided on creation."""
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("key"):
            label = attrs.get("label", "")
            if not label:
                raise serializers.ValidationError(
                    {"label": _("Label is required to auto-generate the key.")}
                )
            company = self.context.get("company")
            base_key = slugify_status_key(label)
            attrs["key"] = make_unique_key(base_key, company) if company else base_key
        return attrs


class ArchiveStatusV2Serializer(serializers.Serializer):
    """
    Input serializer for the archive endpoint.

    `move_to_status_id` is optional:
    - Provided  → batch-move all applications then archive atomically.
    - Omitted   → archive only if the status has no active applications;
                  otherwise return 409 with the count.
    """

    move_to_status_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text=_(
            "UUID of the status to move existing applications to before archiving. "
            "If omitted and the status has applications a 409 is returned."
        ),
    )

    def validate_move_to_status_id(self, value):
        if value is None:
            return value
        company = self.context.get("company")
        try:
            status = ApplicationStatusModel.objects.get(id=value, is_active=True)
        except ApplicationStatusModel.DoesNotExist:
            raise serializers.ValidationError(_("Target status not found."))
        if company and status.company_id != company.id:
            raise serializers.ValidationError(
                _("Target status does not belong to your company.")
            )
        return value

