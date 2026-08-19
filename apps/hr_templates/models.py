from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class Template(AbstractBaseModel):
    """
    A reusable template that recruiters can use for:
    1. Status changes (e.g., rejection reasons, acceptance notes, interview scheduling)
    2. Headhunting invitations (cold reach / invite letters)

    The text from these templates is sent as recruiter_notes when
    changing the status of a job application, or as invitation letters
    when headhunting candidates.

    Supports variable substitution using {{variable_name}} syntax:
    - {{candidate_name}} - Candidate's full name (falls back to email)
    - {{position}} - Job position / vacancy title
    - {{company_name}} - Company name
    """

    class TemplateType(models.TextChoices):
        STATUS_CHANGE = "STATUS_CHANGE", _("Status Change Template")
        INVITATION = "INVITATION", _("Invitation Template")

    id = UUIDField(primary_key=True, version=7, editable=False)

    template_type = models.CharField(
        max_length=20,
        choices=TemplateType.choices,
        default=TemplateType.STATUS_CHANGE,
        verbose_name=_("Template Type"),
        help_text=_("Whether this template is for status changes or invitations"),
    )

    title = models.CharField(
        max_length=255,
        verbose_name=_("Title"),
        help_text=_("Short title for the template"),
    )

    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Detailed description or template text. Supports {{candidate_name}}, {{position}}, {{company_name}} variables."),
    )

    company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.CASCADE,
        related_name="templates",
        verbose_name=_("Company"),
        help_text=_("The company this template belongs to"),
    )

    application_status = models.ForeignKey(
        "applications.ApplicationStatusModel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="templates",
        verbose_name=_("Application Status"),
        help_text=_("The company-specific application status this template is associated with (required for STATUS_CHANGE templates)"),
    )

    class Meta:
        verbose_name = _("Template")
        verbose_name_plural = _("Templates")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["company", "template_type"]),
            models.Index(fields=["company", "template_type", "application_status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "template_type", "application_status"],
                name="unique_status_template_per_company",
                condition=models.Q(template_type="STATUS_CHANGE"),
            ),
        ]

    def clean(self):
        """Validate template fields based on template type."""
        super().clean()

        if self.template_type == self.TemplateType.STATUS_CHANGE:
            if not self.application_status:
                raise ValidationError(
                    _("STATUS_CHANGE templates must have an associated application_status.")
                )
        elif self.template_type == self.TemplateType.INVITATION:
            if self.application_status:
                raise ValidationError(
                    _("INVITATION templates must not have an associated application_status.")
                )

        # Validate that application_status belongs to the same company
        if self.application_status and self.application_status.company_id != self.company_id:
            raise ValidationError(
                _("The application_status must belong to the same company as the template.")
            )

    def __str__(self) -> str:
        return str(self.title)


# Backward compatibility alias
Reason = Template
