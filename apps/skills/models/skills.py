from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError


class SkillCategory(models.Model):
    name = models.CharField(
        max_length=100, unique=True
    )  # "Programming", "Languages", "Soft Skills"
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Skill Categories"

    def clean(self):
        # Prevent lowercase/uppercase duplicates ("Programming" vs "programming")
        self.name = self.name.strip()
        if (
                SkillCategory.objects.filter(name__iexact=self.name)
                        .exclude(pk=self.pk)
                        .exists()
        ):
            raise ValidationError(
                {"name": _("This category already exists (case-insensitive check).")}
            )


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.ManyToManyField(SkillCategory, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_skills",
        help_text=(
            "The user (candidate or recruiter) who submitted this skill. "
            "Used to enforce per-user creation limits."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        ordering = ["category__name", "name"]


class SkillSynonym(models.Model):
    """For handling different names for same skill (JS vs JavaScript)"""

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="synonyms")
    synonym = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.synonym} -> {self.skill.name}"
