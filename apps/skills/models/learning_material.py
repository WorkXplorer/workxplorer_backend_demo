from django.db import models
from django.utils.translation import gettext_lazy as _

from utils import AbstractBaseModel
from utils.fields import UUIDField


class LearningMaterial(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    class MaterialType(models.TextChoices):
        COURSE = "course", _("Course")
        VIDEO = "video", _("Video")
        ARTICLE = "article", _("Article")
        DOCUMENTATION = "documentation", _("Documentation")

    title = models.CharField(max_length=500)
    title_ru = models.CharField(max_length=500, blank=True, default="")
    title_uz = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    material_type = models.CharField(
        max_length=20,
        choices=MaterialType.choices,
        default=MaterialType.COURSE,
    )
    source = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("Source platform, e.g. Coursera, YouTube"),
    )
    url = models.URLField(
        max_length=1000,
        blank=True,
        default="",
    )
    duration_hours = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=0,
        help_text=_("Duration in hours"),
    )
    language = models.CharField(
        max_length=5,
        default="en",
        help_text=_("Content language"),
    )
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=0,
        help_text=_("Average rating (0-5)"),
    )
    is_free = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = _("Learning Material")
        verbose_name_plural = _("Learning Materials")
        ordering = ["-rating", "title"]
        indexes = [
            models.Index(fields=["material_type", "is_active"]),
            models.Index(fields=["source"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["url"],
                name="unique_learning_material_url",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.material_type})"


class SkillLearningMaterial(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7)

    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.CASCADE,
        related_name="learning_materials",
    )
    material = models.ForeignKey(
        LearningMaterial,
        on_delete=models.CASCADE,
        related_name="skill_materials",
    )
    relevance_score = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("AI-computed relevance score (0-100)"),
    )
    is_top_match = models.BooleanField(
        default=False,
        help_text=_("Whether this is a top match for the skill"),
    )
    relevance_reason = models.TextField(
        blank=True,
        default="",
        help_text=_("AI-generated reason for the relevance ranking"),
    )
    vacancy_match_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        default=0,
        help_text=_("Percentage of vacancies this material covers"),
    )

    class Meta:
        verbose_name = _("Skill Learning Material")
        verbose_name_plural = _("Skill Learning Materials")
        ordering = ["-relevance_score"]
        indexes = [
            models.Index(fields=["skill", "-relevance_score"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["skill", "material"],
                name="unique_skill_material",
            )
        ]

    def __str__(self):
        return f"{self.skill.name} → {self.material.title} ({self.relevance_score})"
