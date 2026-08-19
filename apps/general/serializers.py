from rest_framework import serializers

from django.utils.translation import gettext as _

from utils.language import SUPPORTED_LANGUAGES

from .models import Avatar, EmailTemplate


class ProfilePictureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Avatar
        fields = "__all__"


class ManualEmailCampaignSerializer(serializers.Serializer):
    """
    Validates candidate vacancy recommendation email campaign requests.
    """

    template_type = serializers.CharField(
        max_length=50,
        required=True,
        allow_blank=False,
    )
    audience = serializers.CharField(required=False, default="candidates")
    emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        default=list,
    )
    edupartner_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Send to all active candidates belonging to these educational partners (by id).",
    )
    no_university_only = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Send to all active candidates with no educational partner assigned at all "
                   "(candidates only). Combine with emails/edupartner_ids if needed.",
    )
    vacancy_limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=7,
        default=5,
    )
    recipient_limit = serializers.IntegerField(
        required=False,
        min_value=1,
        allow_null=True,
        default=None,
        help_text="Cap how many recipients from the resolved set (emails / edupartner_ids / "
                   "the full active base) actually get emailed. No cap if omitted.",
    )
    cooldown_seconds = serializers.IntegerField(
        required=False,
        min_value=0,
        default=0,
        help_text="Seconds to wait between each successive email. 0 (default) sends "
                   "everything immediately with no pacing.",
    )
    language = serializers.CharField(
        required=False,
        max_length=5,
        allow_blank=False,
    )

    def validate_audience(self, value):
        value = (value or "candidates").strip().lower()
        if value in {"student", "students", "candidate", "candidates"}:
            return "candidates"
        if value in {"recruiter", "recruiters"}:
            return "recruiters"
        raise serializers.ValidationError(_("audience must be candidates or recruiters."))

    def validate_template_type(self, value):
        value = value.strip()
        if not EmailTemplate.objects.filter(template_type=value).exists():
            raise serializers.ValidationError(
                _("EmailTemplate with this template_type does not exist.")
            )

        return value

    def validate_language(self, value):
        value = value.strip().lower()
        if value not in SUPPORTED_LANGUAGES:
            raise serializers.ValidationError(
               _("Unsupported language. Allowed values: uz, ru, en.")
            )
        return value

    def validate(self, attrs):
        emails = attrs.get("emails") or []
        attrs["emails"] = sorted({email.lower().strip() for email in emails})
        attrs["edupartner_ids"] = list({str(v) for v in (attrs.get("edupartner_ids") or [])})

        has_edupartner_filter = bool(attrs["edupartner_ids"]) or attrs.get("no_university_only")

        # No emails and no edupartner_ids means "the entire active base for this
        # audience" — deliberate, always pair with recipient_limit/cooldown_seconds.
        if has_edupartner_filter and attrs.get("audience") == "recruiters":
            raise serializers.ValidationError(
                {"audience": _("edupartner_ids/no_university_only filters only apply to the candidates audience.")}
            )

        return attrs
