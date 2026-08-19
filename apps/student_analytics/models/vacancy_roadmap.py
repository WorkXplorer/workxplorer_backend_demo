from django.db import models
from django.utils.translation import gettext_lazy as _

from utils import AbstractBaseModel
from utils.fields import UUIDField


class VacancySkillRoadmap(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)
    application = models.OneToOneField(
        "applications.JobApplication",
        on_delete=models.CASCADE,
        related_name="vacancy_skill_roadmap",
    )
    rejection_summary = models.JSONField(
        default=dict,
        help_text=_("AI-generated rejection summary in uz/ru/en"),
    )
    ai_model = models.CharField(
        max_length=30,
        default="groq",
    )
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    thinking_tokens = models.PositiveIntegerField(default=0)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Vacancy Skill Roadmap")
        verbose_name_plural = _("Vacancy Skill Roadmaps")
        ordering = ["-generated_at"]

    def __str__(self):
        return f"VacancyRoadmap(app={self.application_id})"


class VacancyRoadmapItem(AbstractBaseModel):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        IN_PROGRESS = "in_progress", _("In progress")
        VERIFIED = "verified", _("Verified")

    id = UUIDField(primary_key=True, version=7)
    roadmap = models.ForeignKey(
        VacancySkillRoadmap,
        on_delete=models.CASCADE,
        related_name="items",
    )
    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vacancy_roadmap_items",
    )
    skill_name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    target_level = models.CharField(max_length=20, default="INTERMEDIATE")
    current_level = models.CharField(max_length=20, default="UNDEFINED")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
        db_index=True,
    )
    is_critical = models.BooleanField(default=False)
    impact_percentage = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    context_message = models.TextField(blank=True, default="")
    learning_time_hours = models.PositiveIntegerField(default=0)
    learning_time_weeks = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Vacancy Roadmap Item")
        verbose_name_plural = _("Vacancy Roadmap Items")
        ordering = ["roadmap", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["roadmap", "skill"],
                name="unique_vacancy_roadmap_skill",
            ),
        ]

    def __str__(self):
        return f"#{self.order} {self.skill_name} ({self.status})"
