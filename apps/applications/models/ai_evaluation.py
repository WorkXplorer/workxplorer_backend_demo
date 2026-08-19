"""
ApplicationAIEvaluation model for storing AI candidate evaluation results.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from utils import AbstractBaseModel
from utils.fields import UUIDField


class EvaluationStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")


class ApplicationAIEvaluation(AbstractBaseModel):
    """
    Stores the AI-powered evaluation result for a job application.

    Created automatically when a JobApplication is submitted.
    Populated asynchronously by an RQ task that calls the AI provider.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    application = models.OneToOneField(
        "applications.JobApplication",
        on_delete=models.CASCADE,
        related_name="ai_evaluation",
        help_text=_("The job application this evaluation belongs to"),
    )
    status = models.CharField(
        max_length=20,
        choices=EvaluationStatus.choices,
        default=EvaluationStatus.PENDING,
        db_index=True,
        help_text=_("Current evaluation status"),
    )
    overall_score = models.FloatField(
        null=True,
        blank=True,
        help_text=_("0-100 match score from AI evaluation"),
    )
    result = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Full AI evaluation JSON result with uz/ru/en translations"),
    )
    detected_language = models.CharField(
        max_length=5,
        default="uz",
        help_text=_("Language code detected from the candidate for this evaluation"),
    )
    input_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text=_("Number of input/prompt tokens used for the AI request"),
    )
    output_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text=_("Number of output/completion tokens returned by the AI"),
    )
    thinking_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("Number of thinking/reasoning tokens used by the AI"),
    )
    job_queue_id = models.UUIDField(
        null=True,
        blank=True,
        help_text=_("Reference to the JobQueue entry tracking this evaluation task"),
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text=_("Error details if evaluation failed"),
    )
    evaluated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp when evaluation was completed"),
    )

    class Meta:
        verbose_name = _("Application AI Evaluation")
        verbose_name_plural = _("Application AI Evaluations")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["overall_score"]),
        ]

    def __str__(self):
        return f"AIEvaluation({self.application_id}) status={self.status} score={self.overall_score}"
