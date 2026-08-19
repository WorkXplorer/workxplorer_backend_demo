from utils.fields import UUIDField

from django.db import models
from django.utils.translation import gettext_lazy as _

from utils import AbstractBaseModel

from apps.domain.models import Domain
from apps.resumes.models.choices import ProficiencyLevel


class EduPartnersType(models.Model):
    """
    Educational partners type model to store types of educational partners. Like College, University, School and etc
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = "Educational Partner Type"
        verbose_name_plural = "Educational Partner Types"


class EduPartner(models.Model):
    """
    Educational partners model to store info about each edu partner.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    name = models.CharField(max_length=350)
    edupartner_type = models.ForeignKey(EduPartnersType, on_delete=models.CASCADE)
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Address"),
        help_text=_("Full address of the educational partner"),
    )
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="edupartner_logos/", blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ({self.edupartner_type.name})"

    class Meta:
        ordering = ["name"]


class Faculty(AbstractBaseModel):
    """
    Faculty model to store information about faculties within educational partners.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    name = models.CharField(
        max_length=255,
        verbose_name=_("Faculty Name"),
        help_text=_("Name of the faculty (e.g., Computer Science, Business)"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the faculty"),
    )
    edupartner = models.ForeignKey(
        "EduPartner",
        on_delete=models.CASCADE,
        related_name="faculties",
        verbose_name=_("Educational Partner"),
        help_text=_("The educational partner this faculty belongs to"),
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faculties",
        verbose_name=_("Domain"),
        help_text=_("The domain associated with this faculty"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Indicates whether the faculty is active"),
    )

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = _("Faculty")
        verbose_name_plural = _("Faculties")
        ordering = ["name"]


class SubjectSkill(models.Model):
    """
    Intermediate model to associate skills with subjects and specify proficiency levels.
    """

    subject = models.ForeignKey(
        "Subject",
        on_delete=models.CASCADE,
        related_name="subject_skills",
        verbose_name=_("Subject"),
    )
    skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.CASCADE,
        related_name="subject_skills",
        verbose_name=_("Skill"),
    )
    proficiency_level = models.CharField(
        max_length=20,
        choices=ProficiencyLevel.choices,
        default=ProficiencyLevel.UNDEFINED,
        verbose_name=_("Proficiency Level"),
        help_text=_("Expected proficiency level acquired after studying this subject"),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "skill"], name="unique_subject_skill"
            )
        ]
        verbose_name = _("Subject Skill")
        verbose_name_plural = _("Subject Skills")

    def __str__(self):
        return f"{self.subject.name} — {self.skill.name} ({self.proficiency_level})"


class Subject(AbstractBaseModel):
    """
    Subject model to store information about subjects within faculties.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    name = models.CharField(
        max_length=255,
        verbose_name=_("Subject Name"),
        help_text=_("Name of the subject (e.g., Data Structures, Marketing)"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Detailed description of the subject"),
    )
    faculty = models.ForeignKey(
        "Faculty",
        on_delete=models.CASCADE,
        related_name="subjects",
        verbose_name=_("Faculty"),
        help_text=_("The faculty this subject belongs to"),
    )
    acquired_skills = models.ManyToManyField(
        "skills.Skill",
        through="SubjectSkill",
        related_name="subjects",
        blank=True,
        verbose_name=_("Acquired Skills"),
        help_text=_("Skills that can be acquired by studying this subject"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active"),
        help_text=_("Indicates whether the subject is active"),
    )

    def __str__(self):
        return f"{self.name}"

    class Meta:
        verbose_name = _("Subject")
        verbose_name_plural = _("Subjects")
        ordering = ["name"]
