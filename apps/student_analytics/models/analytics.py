from django.db import models
from django.utils.translation import gettext_lazy as _

from utils import AbstractBaseModel
from utils.fields import UUIDField


class StudentAnalytics(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    candidate = models.OneToOneField(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="analytics",
    )
    resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.CASCADE,
        related_name="analytics",
    )
    target_role = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_("Target role for analytics, e.g. 'Product Designer'"),
    )
    market_match_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("Percentage match against market requirements"),
    )
    market_match_insight = models.TextField(
        blank=True,
        default="",
        help_text=_("AI-generated insight text explaining the match percentage"),
    )
    track_progress_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("Overall roadmap completion percentage"),
    )
    verified_skills_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of skills verified via tests"),
    )
    total_roadmap_skills = models.PositiveIntegerField(
        default=0,
        help_text=_("Total skills in the roadmap"),
    )
    strong_skills = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Skills the candidate already has that match market demand"),
    )
    skills_to_improve = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Skills the candidate needs to learn or improve"),
    )
    input_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI input tokens used for market match insight"),
    )
    output_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI output tokens used for market match insight"),
    )
    thinking_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI thinking/reasoning tokens used for market match insight"),
    )
    last_computed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When analytics were last recomputed"),
    )

    class Meta:
        verbose_name = _("Student Analytics")
        verbose_name_plural = _("Student Analytics")
        indexes = [
            models.Index(fields=["candidate"]),
            models.Index(fields=["resume"]),
        ]

    def __str__(self):
        return f"Analytics({self.candidate_id}) match={self.market_match_percentage}%"


class SkillRoadmap(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    analytics = models.OneToOneField(
        StudentAnalytics,
        on_delete=models.CASCADE,
        related_name="roadmap",
    )
    target_role = models.CharField(max_length=255, blank=True, default="")
    ai_model = models.CharField(
        max_length=30,
        default="default",
        help_text=_("AI model used to generate this roadmap"),
    )
    input_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI input tokens used for roadmap generation"),
    )
    output_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI output tokens used for roadmap generation"),
    )
    thinking_tokens = models.PositiveIntegerField(
        default=0,
        help_text=_("AI thinking/reasoning tokens used for roadmap generation"),
    )
    generated_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When the roadmap was generated"),
    )

    class Meta:
        verbose_name = _("Skill Roadmap")
        verbose_name_plural = _("Skill Roadmaps")
        ordering = ["-generated_at"]

    def __str__(self):
        return f"Roadmap({self.analytics.candidate_id}) role={self.target_role}"


class RoadmapItem(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        IN_PROGRESS = "in_progress", _("In progress")
        VERIFIED = "verified", _("Verified")

    roadmap = models.ForeignKey(
        SkillRoadmap,
        on_delete=models.CASCADE,
        related_name="items",
    )
    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roadmap_items",
    )
    skill_name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(
        default=0,
        help_text=_("Position in the roadmap sequence"),
    )
    target_level = models.CharField(
        max_length=20,
        default="INTERMEDIATE",
        help_text=_("Target proficiency level"),
    )
    current_level = models.CharField(
        max_length=20,
        default="UNDEFINED",
        help_text=_("Candidate's current proficiency level"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
        db_index=True,
    )
    is_critical = models.BooleanField(
        default=False,
        help_text=_("Whether this skill is critical for the target role"),
    )
    impact_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("AI-estimated impact on hire chances"),
    )
    vacancy_count = models.PositiveIntegerField(
        default=0,
        help_text=_("Number of vacancies requiring this skill"),
    )
    salary_impact_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("Estimated salary impact percentage"),
    )
    learning_time_hours = models.PositiveIntegerField(
        default=0,
        help_text=_("AI-estimated hours to learn this skill"),
    )
    learning_time_weeks = models.PositiveIntegerField(
        default=0,
        help_text=_("AI-estimated weeks to learn this skill"),
    )
    context_message = models.TextField(
        blank=True,
        default="",
        help_text=_("AI-generated context message for the skill detail page"),
    )

    class Meta:
        verbose_name = _("Roadmap Item")
        verbose_name_plural = _("Roadmap Items")
        ordering = ["roadmap", "order"]
        indexes = [
            models.Index(fields=["roadmap", "order"]),
            models.Index(fields=["roadmap", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["roadmap", "skill"],
                name="unique_roadmap_skill",
            )
        ]

    def __str__(self):
        return f"#{self.order} {self.skill_name} ({self.status})"
