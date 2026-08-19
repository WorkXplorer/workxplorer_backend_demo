from rest_framework import serializers
from django.utils.translation import gettext as _
from apps.skills.models import SkillCategory, Skill, SkillSynonym
from apps.skills.localization import (
    localized_skill_name,
    normalize_language,
    skill_create_kwargs,
    skill_name_query,
    user_preferred_language,
)


class SkillCategorySerializer(serializers.ModelSerializer):
    """Serializer for SkillCategory model."""

    class Meta:
        model = SkillCategory
        fields = ("id", "name", "description")

    def validate_name(self, value):
        # Strip spaces and enforce min length
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError(
                _("Category name must be at least 3 characters long.")
            )

        # Case-insensitive duplicate check
        if (
                SkillCategory.objects.filter(name__iexact=value)
                        .exclude(pk=self.instance.pk if self.instance else None)
                        .exists()
        ):
            raise serializers.ValidationError(
                _("This category already exists (case-insensitive check).")
            )

        return value

    def validate(self, attrs):
        # Example: Ensure description is provided if name is too generic
        if attrs["name"].lower() in ["other", "misc", "general"] and not attrs.get(
                "description"
        ):
            raise serializers.ValidationError(
                {
                    "description": _("Description is required for generic categories like 'Other'.")
                }
            )
        return attrs


class SkillSynonymSerializer(serializers.ModelSerializer):
    """Serializer for SkillSynonym model."""

    class Meta:
        model = SkillSynonym
        fields = ["id", "synonym", "skill"]

    def validate(self, data):
        synonym = data["synonym"].strip().lower()
        skill = data["skill"]

        if SkillSynonym.objects.filter(skill=skill, synonym__iexact=synonym).exists():
            raise serializers.ValidationError(
                {"synonym": _("'{synonym}' already exists for this skill").format(synonym=data['synonym'])}
            )
        return data


class SkillSerializer(serializers.ModelSerializer):
    """
    Optimized Skill serializer that reuses prefetched data.
    """

    category = serializers.SerializerMethodField()
    synonyms = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    is_pending = serializers.SerializerMethodField()

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "description",
            "category",
            "synonyms",
            "is_pending",
            "created_at",
        ]

    def get_is_pending(self, obj):
        """True while the skill is awaiting AI approval (``is_active=False``)."""
        return not obj.is_active

    def get_category(self, obj):
        """
        Use prefetched categories without additional queries.
        """
        # Access prefetched data directly
        categories = obj.category.all()
        return SkillCategorySerializer(categories, many=True).data

    def get_synonyms(self, obj):
        """
        Use prefetched synonyms without additional queries.
        """
        # Access prefetched data directly
        synonyms = obj.synonyms.all()
        return SkillSynonymSerializer(synonyms, many=True).data

    def validate_name(self, value):
        """
        Optimized duplicate check - use cached instance from context.
        """
        value = value.strip()

        # Get cached instance from context to avoid extra query
        cached_instance = self.context.get("cached_instance")

        query = Skill.objects.filter(skill_name_query(value)).distinct()

        # Exclude current instance if updating
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        elif cached_instance:
            query = query.exclude(pk=cached_instance.pk)

        # Use .exists() instead of fetching the object
        if query.exists():
            raise serializers.ValidationError(_("A skill with this name already exists."))

        return value

    def get_name(self, obj):
        request = self.context.get("request")
        return localized_skill_name(
            obj,
            user_preferred_language(getattr(request, "user", None)),
        )

    def validate(self, attrs):
        """
        Additional cross-field validation without extra queries.
        """
        return attrs


class SkillCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = str(value or "").strip()
        if not value:
            raise serializers.ValidationError(_("Skill name must not be empty."))

        if self.context.get("skip_duplicate_check"):
            return value

        query = Skill.objects.filter(skill_name_query(value)).distinct()
        if query.exists():
            raise serializers.ValidationError(_("A skill with this name already exists."))

        return value

    def create(self, validated_data):
        skill_name = validated_data.pop("name")
        if self.context.get("store_name_only"):
            validated_data["name"] = skill_name
            return Skill.objects.create(**validated_data)

        request = self.context.get("request")
        language = user_preferred_language(getattr(request, "user", None))
        language = normalize_language(language)
        create_kwargs = skill_create_kwargs(skill_name, language)
        create_kwargs.update(validated_data)
        return Skill.objects.create(**create_kwargs)
