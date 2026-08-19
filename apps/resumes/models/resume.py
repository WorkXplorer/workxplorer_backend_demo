import re
from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.files.storage import default_storage
from django.utils.translation import gettext_lazy as _
from utils.fields import UUIDField
from utils import AbstractBaseModel
from .choices import ProficiencyLevel, LanguageProficiencyLevel, WorkStatus
from pgvector.django import VectorField
import logging
import uuid
import os

logger = logging.getLogger(__name__)


def _sanitize_filename(filename):
    _, ext = os.path.splitext(filename)
    return f"{uuid.uuid4().hex}{ext}"


def certificate_upload_path(instance, filename):
    """Generate upload path for certificate files."""
    return f"certificates/{instance.resume.candidate_id}/{_sanitize_filename(filename)}"


def language_certificate_upload_path(instance, filename):
    """Generate upload path for language certificate files."""
    return f"language_certificates/{instance.resume.candidate_id}/{_sanitize_filename(filename)}"


class ResumeCertificate(AbstractBaseModel):
    """
    Represents certificates attached to a resume.
    """

    resume = models.ForeignKey(
        "Resume",
        on_delete=models.CASCADE,
        related_name="certificates",
        help_text="Resume this certificate belongs to",
    )
    name = models.CharField(
        max_length=200, null=True, blank=True, help_text="Certificate name"
    )
    file = models.FileField(
        upload_to=certificate_upload_path,
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["jpg", "jpeg", "png", "svg", "zip", "pdf"]
            )
        ],
        help_text="Certificate file (max 5MB)",
    )
    issuing_organization = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Organization that issued the certificate",
    )
    issue_date = models.DateField(
        null=True, blank=True, help_text="When the certificate was issued"
    )
    expiration_date = models.DateField(
        null=True, blank=True, help_text="When the certificate expires"
    )
    credential_id = models.CharField(
        max_length=100, null=True, blank=True, help_text="Certificate credential ID"
    )
    credential_url = models.URLField(
        null=True, blank=True, help_text="URL to verify the certificate"
    )

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        verbose_name = "Resume Certificate"
        verbose_name_plural = "Resume Certificates"

    def delete(self, *args, **kwargs):
        """
        Override delete to clean up associated files before deleting the database record.
        """
        if self.file and default_storage.exists(self.file.name):
            try:
                default_storage.delete(self.file.name)
                logger.info(f"Deleted certificate file: {self.file.name}")
            except Exception as e:
                logger.error(f"Failed to delete certificate file {self.file.name}: {e}")

        super().delete(*args, **kwargs)

    def __str__(self):
        if self.name:
            return f"{self.name} - {self.issuing_organization or 'Unknown'}"
        return f"Certificate for {self.resume}"


class ResumeSkill(models.Model):
    resume = models.ForeignKey(
        "Resume", on_delete=models.CASCADE, related_name="resume_skills"
    )
    skill = models.ForeignKey(
        "skills.Skill", on_delete=models.CASCADE, related_name="resume_skills"
    )
    minimum_years = models.PositiveIntegerField(default=0)
    proficiency_level = models.CharField(
        max_length=20,
        choices=ProficiencyLevel.choices,
        default=ProficiencyLevel.UNDEFINED,
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this skill has been verified via a skill test",
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the skill was verified",
    )
    verified_test_attempt = models.ForeignKey(
        "skill_tests.TestAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_resume_skills",
        help_text="The test attempt that verified this skill",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["resume", "skill"], name="unique_resume_skill"
            )
        ]
        verbose_name = "Resume Skill"
        verbose_name_plural = "Resume Skills"

    def __str__(self):
        return f"{self.resume.title} — {self.skill.name} ({self.proficiency_level})"


class ResumeExperience(models.Model):
    resume = models.ForeignKey(
        "Resume", on_delete=models.CASCADE, related_name="experiences"
    )
    company = models.CharField(max_length=140)
    role = models.CharField(max_length=140)
    country = models.CharField(max_length=100, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.role} at {self.company}"


class ResumeContact(models.Model):
    CONTACT_TYPES = [
        ("EMAIL", "Email"),
        ("PHONE", "Phone"),
        ("LINKEDIN", "LinkedIn"),
        ("GITHUB", "GitHub"),
        ("PORTFOLIO", "Portfolio"),
    ]

    resume = models.ForeignKey(
        "Resume", on_delete=models.CASCADE, related_name="contacts"
    )
    type = models.CharField(max_length=20, choices=CONTACT_TYPES)
    value = models.CharField(max_length=255)

    class Meta:
        unique_together = ["resume", "type", "value"]

    def __str__(self):
        return f"{self.get_type_display()}: {self.value}"


class ResumeLanguageCertificate(AbstractBaseModel):
    """
    Represents a language proficiency entry on a resume with optional certificate file.

    Each entry links a resume to a language with a CEFR proficiency level
    and an optional supporting certificate file.

    Constraint: Only one entry per language per resume.
    """

    resume = models.ForeignKey(
        "Resume",
        on_delete=models.CASCADE,
        related_name="language_certificates",
        help_text="Resume this language certificate belongs to",
    )
    language = models.ForeignKey(
        "languages.Language",
        on_delete=models.CASCADE,
        related_name="resume_certificates",
        help_text="Language for this proficiency entry",
    )
    level = models.CharField(
        max_length=2,
        choices=LanguageProficiencyLevel.choices,
        help_text="CEFR proficiency level (A1-C2)",
    )
    file = models.FileField(
        upload_to=language_certificate_upload_path,
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["jpg", "jpeg", "png", "svg", "zip", "pdf"]
            )
        ],
        help_text="Optional certificate file proving proficiency (max 5MB)",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Resume Language Certificate"
        verbose_name_plural = "Resume Language Certificates"
        constraints = [
            models.UniqueConstraint(
                fields=["resume", "language"],
                name="unique_resume_language_certificate",
            )
        ]

    def delete(self, *args, **kwargs):
        """Override delete to clean up associated files."""
        if self.file and default_storage.exists(self.file.name):
            try:
                default_storage.delete(self.file.name)
                logger.info(f"Deleted language certificate file: {self.file.name}")
            except Exception as e:
                logger.error(
                    f"Failed to delete language certificate file {self.file.name}: {e}"
                )
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.language.name} - {self.level} ({self.resume})"


class Resume(AbstractBaseModel):
    class CreatedByType(models.TextChoices):
        AI_GENERATED = "ai_generated", _("AI Generated")
        CANDIDATE_CREATED = "candidate_created", _("Candidate Created")

    id = UUIDField(primary_key=True, version=7, editable=False)

    candidate = models.ForeignKey(
        "authentication.Candidate", on_delete=models.CASCADE, related_name="resumes"
    )

    created_by_type = models.CharField(
        max_length=20,
        choices=CreatedByType.choices,
        default=CreatedByType.CANDIDATE_CREATED,
        help_text=_("Whether the resume was created by AI or by the candidate"),
    )

    title = models.CharField(max_length=140, blank=True, default="")

    description = models.TextField()

    # New required fields based on Figma design
    position = models.CharField(
        max_length=200,
        default="Software Developer",
        help_text="Desired job position/title",
    )
    domain = models.ForeignKey(
        "domain.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resumes",
        help_text="Professional domain/field",
    )
    work_status = models.CharField(
        max_length=30,
        choices=WorkStatus.choices,
        default=WorkStatus.ACTIVELY_LOOKING,
        help_text="Current work seeking status",
    )

    # Employment tracking fields
    current_company_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Name of the company where candidate is currently working",
    )
    current_company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employed_resumes",
        help_text="Reference to company if registered on platform",
    )
    current_position = models.CharField(
        max_length=255, blank=True, null=True, help_text="Current job position/title"
    )
    employment_start_date = models.DateField(
        null=True, blank=True, help_text="Date when candidate started current job"
    )
    current_salary = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current salary (optional, for analytics)",
    )
    salary_currency = models.CharField(
        max_length=5,
        choices=[("USD", "USD"), ("UZS", "UZS"), ("EUR", "EUR")],
        default="UZS",
        help_text="Salary currency",
    )
    salary_hide = models.BooleanField(
        default=False,
        help_text="Whether to hide salary from recruiters/HR views",
    )

    skills = models.ManyToManyField(
        "skills.Skill",
        through="ResumeSkill",
        related_name="resumes",
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    is_reviewed = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True when the candidate has reviewed and accepted this resume. "
                  "AI-generated resumes default to False until the candidate confirms them.",
    )

    is_main = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this is the candidate's main/primary resume",
    )

    combined_text_en = models.TextField(
        blank=True,
        null=True,
        help_text="Combined English text used for embedding generation",
    )

    embedding = VectorField(
        dimensions=384,
        null=True,
        blank=True,
        help_text="Vector embedding of combined_text_en",
    )

    is_embedded = models.BooleanField(
        default=False, db_index=True, help_text="Whether embedding has been generated"
    )

    @staticmethod
    def _strip_html(text):
        return re.sub(r"<[^>]+>", " ", text or "").strip()

    def get_text_for_embedding(self):
        """Generate structured text for embedding."""
        parts = []

        if self.title:
            parts.append(f"Title: {self.title}")

        if self.description:
            parts.append(f"Description: {self._strip_html(self.description)}")

        skill_names = list(
            self.resume_skills.select_related("skill")
            .values_list("skill__name", flat=True)
        )
        if skill_names:
            parts.append(f"Skills: {', '.join(skill_names)}")

        return "\n\n".join(parts)

    def save(self, *args, **kwargs):
        """
        Override save to:
        1. Auto-set first reviewed resume as main on INSERT
        2. Auto-promote to main on UPDATE if candidate has no main resume yet
        3. Ensure only one main resume per candidate
        """

        # Check if this is a new resume (not yet in database).
        # self.pk is None doesn't work for UUID PKs (assigned before save),
        # so use Django's internal _state.adding flag instead.
        is_new = self._state.adding

        if is_new and self.candidate_id and self.is_reviewed:
            existing_count = Resume.objects.filter(
                candidate_id=self.candidate_id
            ).count()
            if existing_count == 0:
                self.is_main = True

        # On any save: if this resume is reviewed but not main, and the
        # candidate has no main resume at all, promote it automatically.
        # This covers accepting an AI-generated resume that was created
        # before the first-resume logic could fire.
        if not self.is_main and self.candidate_id and self.is_reviewed:
            has_main = Resume.objects.filter(
                candidate_id=self.candidate_id, is_main=True
            ).exclude(id=self.id).exists()
            if not has_main:
                self.is_main = True

        # If this resume is being set as main, unset all others
        if self.is_main and self.candidate_id:
            Resume.objects.filter(candidate_id=self.candidate_id, is_main=True).exclude(
                id=self.id
            ).update(is_main=False)

        super().save(*args, **kwargs)

    def is_employed(self):
        """Check if candidate is currently employed based on work_status."""
        return WorkStatus.is_employed(self.work_status)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_embedded", "created_at"]),
            models.Index(fields=["candidate"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["title"]),
            models.Index(fields=["work_status"]),
            models.Index(fields=["candidate", "is_main"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.candidate})"
