from rest_framework import serializers
from django.utils.translation import gettext as _

from apps.skills.models import Skill


class PassiveSkillListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing passive skills."""

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "name_ru",
            "name_uz",
            "description",
            "created_at",
        ]


class AIActionRequestSerializer(serializers.Serializer):
    """Validates the POST request body for AI actions (skill validation / vacancy creation)."""

    STATUS_CHOICES = ("passive_skills", "create_vacancy", "draft_template")
    AI_MODEL_CHOICES = ("default",)
    TEMPLATE_SECTION_CHOICES = ("invitation", "interview", "rejection")

    status = serializers.ChoiceField(
        choices=STATUS_CHOICES,
        required=True,
        error_messages={
            "required": _("The 'status' field is required."),
            "invalid_choice": _(
                "Invalid status. Supported values: {choices}"
            ).format(choices=", ".join(STATUS_CHOICES)),
        },
    )
    ai_model = serializers.ChoiceField(
        choices=AI_MODEL_CHOICES,
        required=True,
        error_messages={
            "required": _("The 'ai_model' field is required."),
            "invalid_choice": _(
                "Invalid ai_model. Supported values: {choices}"
            ).format(choices=", ".join(AI_MODEL_CHOICES)),
        },
    )
    vacancy_url = serializers.URLField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text=_("URL of an external vacancy page to fetch and parse (e.g. hh.uz)."),
    )
    vacancy_body = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text=_("Raw vacancy description text when not using a URL."),
    )
    template_section = serializers.ChoiceField(
        choices=TEMPLATE_SECTION_CHOICES,
        required=False,
        allow_null=True,
        default=None,
        help_text=_("Which template section to draft (for status 'draft_template')."),
    )
    instruction = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default="",
        max_length=1000,
        help_text=_("Optional extra instruction to steer the AI draft."),
    )
    locale = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default="ru",
        max_length=5,
        help_text=_("Target language for the draft ('ru', 'en', 'uz')."),
    )

    def validate(self, data):
        if data.get("status") == "create_vacancy":
            if not data.get("vacancy_url") and not data.get("vacancy_body"):
                raise serializers.ValidationError(
                    _(
                        "Either 'vacancy_url' or 'vacancy_body' is required "
                        "when status is 'create_vacancy'."
                    )
                )
        if data.get("status") == "draft_template" and not data.get("template_section"):
            raise serializers.ValidationError(
                {
                    "template_section": _(
                        "'template_section' is required when status is 'draft_template'."
                    )
                }
            )
        return data


class SkillApprovalDetailSerializer(serializers.Serializer):
    """Single skill result detail."""

    skill_id = serializers.IntegerField()
    approved = serializers.BooleanField()
    duplicate_of_skill_id = serializers.IntegerField(allow_null=True)
    name_en = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    error = serializers.CharField(allow_blank=True, required=False)


class SkillApprovalResultSerializer(serializers.Serializer):
    """Serializes the overall validation result."""

    message = serializers.CharField()
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    duplicates = serializers.IntegerField()
    details = SkillApprovalDetailSerializer(many=True)
