"""
Serializers for the flexible application status system.

This module provides serializers for:
- StatusCategory (read-only, for analytics categories)
- ApplicationStatusModel (CRUD for custom statuses)
- StatusTemplate (for status templates)
"""

from rest_framework import serializers
from django.utils.translation import gettext as _

from apps.applications.models import (
    StatusCategory,
    ApplicationStatusModel,
    StatusTemplate,
)
from utils.language import get_request_language


class StatusCategorySerializer(serializers.ModelSerializer):
    """
    Read-only serializer for analytics status categories.
    
    Categories are system-defined and immutable. They provide the
    mapping layer that allows analytics to work with custom statuses.
    """
    
    class Meta:
        model = StatusCategory
        fields = [
            'key',
            'label',
            'description',
            'is_terminal',
            'is_positive_outcome',
            'is_single_column',
            'position',
        ]
        read_only_fields = fields


class ApplicationStatusSerializer(serializers.ModelSerializer):
    """
    Serializer for company application statuses.
    
    Used for:
    - Listing all statuses for a company
    - Creating new custom statuses
    - Updating status properties (label, color, position)
    """
    
    # Nested category info (read-only)
    category = StatusCategorySerializer(read_only=True)
    category_key = serializers.CharField(
        write_only=True,
        required=False,
        help_text=_("Category key for analytics (e.g., 'HIRED', 'SCREENING')")
    )
    
    # Localized label based on request language
    localized_label = serializers.SerializerMethodField()
    
    # Read-only computed fields
    is_terminal = serializers.BooleanField(
        read_only=True,
        source='category.is_terminal',
        help_text=_("Whether this status ends the application process")
    )
    
    class Meta:
        model = ApplicationStatusModel
        fields = [
            'id',
            'key',
            'label',
            'localized_label',
            'translations',
            'category',
            'category_key',
            'color',
            'position',
            'show_in_kanban',
            'is_active',
            'is_default',
            'is_terminal',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'is_default',
            'is_terminal',
            'created_at',
            'updated_at',
        ]
    
    def get_localized_label(self, obj) -> str:
        """Return the label in the current request language."""
        language = get_request_language()
        return obj.get_localized_label(language)
    
    def validate_key(self, value: str) -> str:
        """Normalize and validate the status key."""
        # Normalize: uppercase, replace spaces/hyphens with underscores
        normalized = value.upper().replace(' ', '_').replace('-', '_')
        
        # Must be alphanumeric with underscores only
        if not normalized.replace('_', '').isalnum():
            raise serializers.ValidationError(
                _("Key must contain only letters, numbers, and underscores.")
            )
        
        return normalized
    
    def validate_color(self, value: str) -> str:
        """Validate hex color format."""
        if not value.startswith('#'):
            value = f'#{value}'
        
        if len(value) != 7:
            raise serializers.ValidationError(
                _("Color must be a 6-character hex code (e.g., '#3B82F6').")
            )
        
        # Validate hex characters
        try:
            int(value[1:], 16)
        except ValueError:
            raise serializers.ValidationError(
                _("Invalid hex color code.")
            )
        
        return value.upper()
    
    def validate_category_key(self, value: str) -> str:
        """Validate that category exists."""
        if not StatusCategory.objects.filter(key=value).exists():
            valid_categories = list(
                StatusCategory.objects.values_list('key', flat=True)
            )
            raise serializers.ValidationError(
                _("Invalid category '{value}'. Valid categories: {valid}").format(
                    value=value,
                    valid=', '.join(valid_categories),
                )
            )
        return value

    def validate(self, attrs):
        """Require category_key when creating a status."""
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get('category_key'):
            raise serializers.ValidationError(
                {'category_key': _("This field is required when creating a status.")}
            )
        return attrs
    
    def create(self, validated_data):
        """Create a new custom status with single-column enforcement."""
        category_key = validated_data.pop('category_key', None)
        
        if category_key:
            category = StatusCategory.objects.get(key=category_key)
            validated_data['category'] = category

            # Single-column enforcement: prevent duplicate statuses in single-column categories
            company = self.context.get('company') or validated_data.get('company')
            if category.is_single_column and company:
                existing = ApplicationStatusModel.objects.filter(
                    company=company,
                    category=category,
                    is_active=True,
                ).exists()
                if existing:
                    raise serializers.ValidationError(
                        _("Category '{category}' only allows one status column. "
                          "A status already exists for this category.").format(
                            category=category.label
                        )
                    )
        
        # Company should be set by the view
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update a status (cannot change key or category)."""
        # Remove fields that cannot be changed
        validated_data.pop('key', None)
        validated_data.pop('category_key', None)
        
        return super().update(instance, validated_data)


class ApplicationStatusMinimalSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for status references in other serializers.
    
    Use this when you need to include status info in application
    responses without the full category details.
    """
    
    localized_label = serializers.SerializerMethodField()
    category_key = serializers.CharField(source='category.key', read_only=True)
    
    class Meta:
        model = ApplicationStatusModel
        fields = [
            'id',
            'key',
            'label',
            'localized_label',
            'category_key',
            'color',
        ]
        read_only_fields = fields
    
    def get_localized_label(self, obj) -> str:
        """Return the label in the current request language."""
        language = get_request_language()
        return obj.get_localized_label(language)


class StatusTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for status templates.
    
    Templates define a set of statuses and transition rules that
    can be applied to a company.
    """
    
    statuses_count = serializers.SerializerMethodField()
    transitions_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StatusTemplate
        fields = [
            'id',
            'name',
            'description',
            'is_default',
            'is_active',
            'statuses',
            'transitions',
            'statuses_count',
            'transitions_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_statuses_count(self, obj) -> int:
        """Return the number of statuses in the template."""
        return len(obj.statuses) if obj.statuses else 0
    
    def get_transitions_count(self, obj) -> int:
        """Return the number of transition rules in the template."""
        return len(obj.transitions) if obj.transitions else 0


class StatusTemplateMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for template selection dropdowns."""
    
    statuses_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StatusTemplate
        fields = [
            'id',
            'name',
            'description',
            'is_default',
            'statuses_count',
        ]
        read_only_fields = fields
    
    def get_statuses_count(self, obj) -> int:
        return len(obj.statuses) if obj.statuses else 0


class StatusReorderSerializer(serializers.Serializer):
    """
    Serializer for bulk reordering statuses.
    
    Accepts a list of status IDs in the desired order.
    """
    
    status_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text=_("List of status IDs in the desired display order"),
    )
    
    def validate_status_ids(self, value):
        """Validate all status IDs belong to the company."""
        company = self.context.get('company')
        if not company:
            raise serializers.ValidationError(
                _("Company context is required.")
            )
        
        # Get existing status IDs for this company
        existing_ids = set(
            ApplicationStatusModel.objects.filter(
                company=company,
                is_active=True,
            ).values_list('id', flat=True)
        )
        
        # Check all provided IDs exist
        provided_ids = set(value)
        invalid_ids = provided_ids - existing_ids
        
        if invalid_ids:
            raise serializers.ValidationError(
                _("Invalid status IDs: {ids}").format(
                    ids=', '.join(str(id) for id in invalid_ids)
                )
            )
        
        return value
    
    def save(self):
        """Update status positions based on the order provided."""
        status_ids = self.validated_data['status_ids']
        
        for position, status_id in enumerate(status_ids, start=1):
            ApplicationStatusModel.objects.filter(
                id=status_id
            ).update(position=position)
        
        return len(status_ids)
