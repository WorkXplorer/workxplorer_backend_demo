from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from apps.hr_templates.constants import (
    ALL_VARIABLES,
    get_unknown_variables,
)
from apps.hr_templates.models import Template


class TemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for full Template CRUD operations.
    The company field is set automatically from the authenticated recruiter.
    """
    template_type_display = serializers.CharField(source="get_template_type_display", read_only=True)
    application_status_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    application_status = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = [
            "id",
            "template_type",
            "template_type_display",
            "title",
            "description",
            "application_status_id",
            "application_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_application_status(self, obj):
        """Return minimal application status info."""
        if obj.application_status:
            return {
                "id": str(obj.application_status.id),
                "key": obj.application_status.key,
                "label": obj.application_status.label,
            }
        return None

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(_("Title cannot be empty."))
        return value

    def validate_description(self, value):
        unknown = get_unknown_variables(value)
        if unknown:
            raise serializers.ValidationError(
                _("Unknown variable(s): %(variables)s. Allowed: %(allowed)s.")
                % {
                    "variables": ", ".join(sorted(unknown)),
                    "allowed": ", ".join(sorted(ALL_VARIABLES)),
                }
            )
        return value

    def validate(self, data):
        """
        Validate template_type and application_status_id consistency,
        and resolve application_status_id to the actual ApplicationStatusModel instance.

        Resolving here (rather than in the view) prevents orphaned records
        that could occur if the view saves to DB before validating the FK.
        """
        if self.instance is None:
            # CREATE path — always validate
            template_type = data.get("template_type", Template.TemplateType.STATUS_CHANGE)
            app_status_id = data.get("application_status_id")

            if template_type == Template.TemplateType.STATUS_CHANGE:
                if not app_status_id:
                    raise serializers.ValidationError(
                        {"application_status_id": _("STATUS_CHANGE templates require an application_status.")}
                    )
            elif template_type == Template.TemplateType.INVITATION:
                if app_status_id:
                    raise serializers.ValidationError(
                        {"application_status_id": _("INVITATION templates must not have an application_status.")}
                    )

            if app_status_id:
                self._resolve_application_status(data, company_source="request")
        else:
            # UPDATE path — only validate if these fields are being changed
            if "application_status_id" in data or "template_type" in data:
                template_type = data.get("template_type", self.instance.template_type)
                app_status_id = data.get("application_status_id")

                if template_type == Template.TemplateType.STATUS_CHANGE:
                    has_status = app_status_id or (
                        "application_status_id" not in data
                        and self.instance
                        and self.instance.application_status_id
                    )
                    if not has_status:
                        raise serializers.ValidationError(
                            {"application_status_id": _("STATUS_CHANGE templates require an application_status.")}
                        )
                elif template_type == Template.TemplateType.INVITATION:
                    has_status = app_status_id or (
                        "application_status_id" not in data
                        and self.instance
                        and self.instance.application_status_id
                    )
                    if has_status:
                        raise serializers.ValidationError(
                            {
                                "application_status_id": _(
                                    "INVITATION templates must not have an application_status. "
                                    "Set application_status_id to null to clear it."
                                )
                            }
                        )

                if app_status_id:
                    self._resolve_application_status(data, company_source="instance")

        return data

    def _resolve_application_status(self, data, company_source):
        """
        Resolve application_status_id to an ApplicationStatusModel instance
        and store it in data['application_status'].
        """
        from apps.applications.models import ApplicationStatusModel

        app_status_id = data.get("application_status_id")
        if company_source == "request":
            from apps.authentication.models import Recruiter
            try:
                request = self.context.get("request")
                if not request or not request.user.is_authenticated:
                    raise serializers.ValidationError(
                        {"application_status_id": _("Authentication required.")}
                    )
                recruiter = Recruiter.objects.select_related("company").get(id=request.user.id)
                company = recruiter.company
            except Recruiter.DoesNotExist:
                raise serializers.ValidationError(
                    {"application_status_id": _("Authenticated user is not a recruiter.")}
                )
        else:
            company = self.instance.company

        try:
            status = ApplicationStatusModel.objects.get(id=app_status_id, company=company)
            data["application_status"] = status
            data.pop("application_status_id")
        except ApplicationStatusModel.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "application_status_id": _(
                        "Application status with id '%(id)s' not found for your company."
                    )
                    % {"id": app_status_id}
                }
            )

    def create(self, validated_data):
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)



