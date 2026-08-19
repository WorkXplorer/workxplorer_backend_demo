import re

from rest_framework import serializers
from django.utils.translation import gettext as _
from .models import Domain
from .models import HrCreatedProfession
from utils.language import get_request_language

# Pattern to detect path traversal sequences and dangerous characters
_PATH_TRAVERSAL_RE = re.compile(r"\.\./|\.\.\\|%2e%2e|%00|\\x00|/etc/|/proc/|/dev/")


class DomainSerializer(serializers.ModelSerializer):
    """Serializer for Domain model with all fields."""

    class Meta:
        model = Domain
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        """Ensure name is not empty and properly formatted."""
        if not value or not value.strip():
            raise serializers.ValidationError(_("Name cannot be empty."))
        return value.strip()


class DomainListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing domains."""
    name = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = ["id", "name"]

    def get_name(self, obj):
        language = get_request_language()

        if language == "ru":
            return obj.name_ru
        elif language == "uz":
            return obj.name_uz
        return obj.name_en


class HrCreatedProfessionSerializer(serializers.ModelSerializer):
    """Serializer for HrCreatedProfession model."""

    class Meta:
        model = HrCreatedProfession
        fields = [
            "id",
            "company",
            "name",
            "description",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        """Ensure profession name is not empty, properly formatted, and safe."""
        if not value or not value.strip():
            raise serializers.ValidationError(_("Profession name cannot be empty."))
        value = value.strip()
        if _PATH_TRAVERSAL_RE.search(value):
            raise serializers.ValidationError(
                _("Name contains invalid characters or sequences.")
            )
        return value

    def validate_description(self, value):
        """Ensure description is not overly long."""
        if value and len(value) > 500:
            raise serializers.ValidationError(
                _("Description cannot exceed 500 characters.")
            )
        return value

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "company_id": getattr(instance, "company_id", None),
            "name": instance.name,
            "description": instance.description,
            "created_by_id": getattr(instance, "created_by_id", None),
            "created_at": (
                instance.created_at.isoformat() if instance.created_at else None
            ),
            "updated_at": (
                instance.updated_at.isoformat() if instance.updated_at else None
            ),
        }
