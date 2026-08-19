import logging
import re
from utils.fields import UUIDField
from django.db import models
from django.utils import timezone
from datetime import timedelta
from apps.skills.models import Skill
from pgvector.django import VectorField
from apps.domain.models import Domain
from apps.profiles.models import RecruiterProfile
from utils import AbstractBaseModel
from apps.resumes.models.choices import LanguageProficiencyLevel

logger = logging.getLogger(__name__)


class FavouriteVacancy(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7, editable=False)
    candidate = models.ForeignKey(
        "authentication.Candidate",
        on_delete=models.CASCADE,
        related_name="favourite_vacancy_entries",
    )
    vacancy = models.ForeignKey(
        "vacancies.Vacancy",
        on_delete=models.CASCADE,
        related_name="favourite_vacancy_entries",
    )

    class Meta:
        verbose_name = "Favourite Vacancy"
        verbose_name_plural = "Favourite Vacancies"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "vacancy"],
                name="unique_candidate_favourite_vacancy",
            )
        ]
        indexes = [
            models.Index(fields=["candidate", "created_at"]),
            models.Index(fields=["vacancy"]),
        ]


class VacancyView(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7, editable=False)
    vacancy = models.ForeignKey("vacancies.Vacancy", on_delete=models.CASCADE)
    candidate = models.ForeignKey("authentication.Candidate", on_delete=models.CASCADE)
    session_start = models.DateTimeField(auto_now_add=True)
    session_end = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.session_end and self.session_start:
            delta = self.session_end - self.session_start
            self.duration_seconds = delta.total_seconds()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Vacancy View"
        verbose_name_plural = "Vacancy Views"
        indexes = [
            models.Index(fields=["vacancy"]),
            models.Index(fields=["candidate"]),
            models.Index(fields=["session_start"]),
        ]
        unique_together = ["vacancy", "candidate", "session_start"]


class VacancySkill(models.Model):
    vacancy = models.ForeignKey("Vacancy", on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    is_required = models.BooleanField(default=True)
    minimum_years = models.IntegerField(default=0, null=True, blank=True)
    proficiency_level = models.CharField(
        max_length=20,
        choices=[
            ("UNDEFINED", "Undefined"),
            ("BEGINNER", "Beginner"),
            ("INTERMEDIATE", "Intermediate"),
            ("ADVANCED", "Advanced"),
            ("EXPERT", "Expert"),
        ],
        default="UNDEFINED",
    )

    class Meta:
        unique_together = ["vacancy", "skill"]


class VacancyLanguage(AbstractBaseModel):
    """
    Required language entry for a vacancy.

    Links a vacancy to a language with a required CEFR proficiency level.
    Constraint: only one entry per language per vacancy.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    vacancy = models.ForeignKey(
        "Vacancy",
        on_delete=models.CASCADE,
        related_name="vacancy_languages",
        help_text="Vacancy this language requirement belongs to",
    )
    language = models.ForeignKey(
        "languages.Language",
        on_delete=models.CASCADE,
        related_name="vacancy_requirements",
        help_text="Required language",
    )
    level = models.CharField(
        max_length=2,
        choices=LanguageProficiencyLevel.choices,
        help_text="Required CEFR proficiency level (A1-C2)",
    )

    class Meta:
        verbose_name = "Vacancy Language"
        verbose_name_plural = "Vacancy Languages"
        constraints = [
            models.UniqueConstraint(
                fields=["vacancy", "language"],
                name="unique_vacancy_language",
            )
        ]

    def __str__(self):
        return f"{self.vacancy.title} — {self.language.name} ({self.level})"


class Vacancy(models.Model):
    id = UUIDField(primary_key=True, version=7, editable=False)
    created_by = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.PROTECT,
        related_name="vacancies",
        null=False,
        blank=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=240)
    domain = models.ForeignKey(
        Domain,
        on_delete=models.PROTECT,
        related_name="vacancies",
        null=True,
        blank=True,
    )
    company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.CASCADE,
        related_name="vacancies",
        null=False,
        blank=False,
    )
    experience = models.IntegerField(default=0)
    contact_email = models.CharField(max_length=50, null=True, blank=True)
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    salary_min = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    salary_max = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    salary_currency = models.CharField(
        max_length=5,
        choices=[("USD", "USD"), ("UZS", "UZS"), ("EUR", "EUR")],
        default="UZS",
    )
    employment_type = models.CharField(
        max_length=30,
        choices=[
            ("FULL_TIME", "Full Time"),
            ("PART_TIME", "Part Time"),
            ("CONTRACT", "Contract"),
            ("INTERNSHIP", "Internship"),
        ],
        default="FULL_TIME",
    )
    employment_format = models.CharField(
        max_length=30,
        choices=[("ON_SITE", "On-site"), ("REMOTE", "Remote"), ("HYBRID", "Hybrid")],
        default="ON_SITE",
    )
    about_us = models.TextField(null=False, blank=False, default="", max_length=10000)
    requirements = models.TextField(null=False, blank=False, default="", max_length=10000)
    responsibilities = models.TextField(null=False, blank=False, default="", max_length=10000)
    additional_info = models.TextField(null=True, blank=True, default="", max_length=10000)
    required_skills = models.ManyToManyField(
        Skill,
        through="VacancySkill",
        related_name="vacancies",
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    number_of_positions = models.PositiveIntegerField(
        default=1,
        help_text="Number of specialists HR wants to hire for this vacancy",
    )
    minimum_ai_score = models.PositiveSmallIntegerField(
        default=40,
        help_text="Minimum AI evaluation score (0-100) for auto-acceptance. Applications below this threshold are auto-rejected.",
    )

    # Embedding
    combined_text_en = models.TextField(
        blank=True,
        null=True,
        help_text="Combined English text used for embedding generation (title + requirements + etc)",
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
    expire = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Expiration date for the vacancy",
        default=100
    )
    location = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Human-readable location name (e.g., city, region)",
    )  
    longitude = models.DecimalField(
        max_digits=30,
        decimal_places=15,
        null=True,
        blank=True,
        help_text="Longitude for geospatial queries",
    )
    latitude = models.DecimalField(
        max_digits=30,
        decimal_places=15,
        null=True,
        blank=True,
        help_text="Latitude for geospatial queries",
    )
    is_demo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="If True, this vacancy is demo/placeholder data shown to unapproved companies.",
    )

    @staticmethod
    def _strip_html(text):
        return re.sub(r"<[^>]+>", " ", text or "").strip()

    def get_text_for_embedding(self):
        """Generate structured text for embedding."""
        parts = []

        if self.title:
            parts.append(f"Title: {self.title}")

        if self.requirements:
            parts.append(f"Requirements: {self._strip_html(self.requirements)}")

        if self.responsibilities:
            parts.append(f"Responsibilities: {self._strip_html(self.responsibilities)}")

        skill_names = list(
            self.vacancyskill_set.select_related("skill")
            .values_list("skill__name", flat=True)
        )
        if skill_names:
            parts.append(f"Skills: {', '.join(skill_names)}")

        return "\n\n".join(parts)

    def expire_vacancy(self):
        """
        Check if vacancy has exceeded its expiration period.
        
        Returns:
            False: If vacancy has expired (is_active set to False)
            True: If vacancy is still active (is_active set to True if it was previously expired)
        """
        expiration_days = self.expire if self.expire is not None else 30

        if timezone.now() - self.created_at >= timedelta(days=expiration_days):
            self.is_active = False
            self.save(update_fields=["is_active"])
            logger.info(f"Vacancy {self.id} expired and deactivated.")
            return False
        else:
            if not self.is_active:
                self.is_active = True
                self.save(update_fields=["is_active"])
                logger.info(f"Vacancy {self.id} reactivated after expire date extension.")
            else:
                logger.info(f"Vacancy {self.id} is still active.")
            return True

    def is_vacancy_expired(self):
        """
        Check if vacancy has exceeded its expiration period (read-only check).
        Does not modify the vacancy.
        
        Returns:
            True: If vacancy has expired
            False: If vacancy is still active (not expired)
        """
        expiration_days = self.expire if self.expire is not None else 30
        return timezone.now() - self.created_at >= timedelta(days=expiration_days)

    def __str__(self):
        return f"{self.title} from {self.company}, created at {self.created_at}"

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_embedded", "created_at"]),
            models.Index(fields=["company"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["employment_type"]),
            models.Index(fields=["is_active"])
        ]

    @classmethod
    def get_open_vacancies_count(cls, end_date=None, company_id=None):
        """
        Get count of open vacancies up to a specific date.
        Uses is_active field instead of status.

        Args:
            end_date: End date for filtering (default: now)
            company_id: Optional company ID to filter by (default: all companies)
        """
        if end_date is None:
            end_date = timezone.now()

        queryset = cls.objects.filter(
            created_at__lte=end_date,
            is_active=True,  # Use is_active instead of status='open'
        )

        if company_id is not None:
            queryset = queryset.filter(company_id=company_id)

        return queryset.count()

    @classmethod
    def get_open_vacancies_comparison(
            cls, current_end_date, previous_end_date, company_id=None
    ):
        """
        Compare open vacancies between two periods.

        Args:
            current_end_date: End date for current period
            previous_end_date: End date for previous period
            company_id: Optional company ID to filter by (default: all companies)
        """
        current_count = cls.get_open_vacancies_count(
            current_end_date, company_id=company_id
        )
        previous_count = cls.get_open_vacancies_count(
            previous_end_date, company_id=company_id
        )

        # Calculate percentage change (JSON-safe)
        if previous_count == 0:
            percentage_change = None  # Use None instead of float('inf')
        else:
            percentage_change = (
                                        (current_count - previous_count) / previous_count
                                ) * 100
            percentage_change = round(percentage_change, 1)

        return {
            "current_count": current_count,
            "previous_count": previous_count,
            "percentage_change": percentage_change,
            "absolute_change": current_count - previous_count,
        }

    @classmethod
    def get_vacancy_views_metrics(
            cls, start_date, end_date, unique_visitors_only=False
    ):
        """
        Get vacancy views metrics for the specified period.

        Args:
            start_date: Start of the period
            end_date: End of the period
            unique_visitors_only: If True, count unique visitors only. If False, count all view events.

        Returns:
            dict: Views metrics
        """

        views_queryset = VacancyView.objects.filter(
            session_start__range=[start_date, end_date],
            duration_seconds__gte=1,  # Only meaningful views
            duration_seconds__lte=1200,  # Exclude sessions > 20 minutes
        ).exclude(duration_seconds__isnull=True)

        if unique_visitors_only:
            # Count unique visitors (distinct candidates per vacancy)
            unique_views = (
                views_queryset.values("vacancy", "candidate").distinct().count()
            )
            total_views = unique_views
        else:
            # Count all view events
            total_views = views_queryset.count()
            unique_views = (
                views_queryset.values("vacancy", "candidate").distinct().count()
            )

        return {
            "total_views": total_views,
            "unique_views": unique_views,
            "total_vacancies_viewed": views_queryset.values("vacancy")
            .distinct()
            .count(),
            "unique_viewers": views_queryset.values("candidate").distinct().count(),
        }

    @classmethod
    def get_views_comparison(
            cls,
            current_start,
            current_end,
            previous_start,
            previous_end,
            unique_visitors_only=False,
    ):
        """
        Compare vacancy views between two periods.

        Args:
            current_start: Start date of current period
            current_end: End date of current period
            previous_start: Start date of previous period
            previous_end: End date of previous period
            unique_visitors_only: Whether to count unique visitors only

        Returns:
            dict: Comparison data
        """
        current_metrics = cls.get_vacancy_views_metrics(
            current_start, current_end, unique_visitors_only
        )
        previous_metrics = cls.get_vacancy_views_metrics(
            previous_start, previous_end, unique_visitors_only
        )

        current_count = current_metrics["total_views"]
        previous_count = previous_metrics["total_views"]

        # Calculate percentage change
        if previous_count == 0:
            percentage_change = None if current_count == 0 else float("inf")
        else:
            percentage_change = (
                                        (current_count - previous_count) / previous_count
                                ) * 100

        return {
            "current_metrics": current_metrics,
            "previous_metrics": previous_metrics,
            "percentage_change": percentage_change,
            "absolute_change": current_count - previous_count,
        }

    @property
    def get_fio_recruiter(self):
        """
        Get full name of the recruiter who created the vacancy.
        """
        try:
            recruiter_profile = RecruiterProfile.objects.get(user=self.created_by)
            return recruiter_profile.full_name or "Unknown Recruiter"
        except RecruiterProfile.DoesNotExist:
            return "Unknown Recruiter"
