from django.db import models
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from utils.fields import UUIDField
from utils import AbstractBaseModel


class CandidateProfile(AbstractBaseModel):
    class RegionChoices(models.TextChoices):
        ANDIJAN = "Andijon", "Andijon"
        BUKHARA = "Buxoro", "Buxoro"
        JIZZAKH = "Jizzax", "Jizzax"
        KASHKADARYA = "Qashqadaryo", "Qashqadaryo"
        NAVOI = "Navoiy", "Navoiy"
        NAMANGAN = "Namangan", "Namangan"
        SAMARKAND = "Samarqand", "Samarqand"
        SIRDARYA = "Sirdaryo", "Sirdaryo"
        SURKHANDARYA = "Surxondaryo", "Surxondaryo"
        TASHKENT_CITY = "Toshkent shahar", "Toshkent shahar"
        TASHKENT_REGION = "Toshkent viloyati", "Toshkent viloyati"
        FERGANA = "Farg'ona", "Farg'ona"
        KHOREZM = "Xorazm", "Xorazm"

    id = UUIDField(primary_key=True, version=7, editable=False)
    candidate = models.OneToOneField(
        "authentication.Candidate", on_delete=models.CASCADE
    )
    phone = models.CharField(max_length=20, null=True, blank=True)
    candidate_email = models.EmailField(null=True, blank=True)
    full_name = models.CharField(max_length=500)
    photo = models.ImageField(upload_to="candidate_photos/", null=True, blank=True)
    address = models.CharField(
        help_text="Full address of the candidate",
        max_length=255,
        null=True,
        blank=True,
    )
    region = models.CharField(
        help_text="Region in Uzbekistan",
        max_length=255,
        choices=RegionChoices.choices,
        default=RegionChoices.TASHKENT_CITY,
    )
    education = models.JSONField(null=True, blank=True)
    citizenship = models.ForeignKey(
        "profiles.Citizenship",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidate_profiles",
        help_text="Candidate's citizenship",
    )
    github_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^(https?://)?github\.com/[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?/?$',
                message=_("Enter a valid GitHub profile URL (e.g., github.com/username)."),
                code='invalid_github_url',
            ),
        ],
        help_text=_("GitHub profile URL (e.g., github.com/username)."),
    )
    linkedin_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^(https?://)?(www\.)?linkedin\.com/(in|company)/[a-zA-Z0-9\-%]+/?$',
                message=_("Enter a valid LinkedIn profile URL (e.g., linkedin.com/in/username)."),
                code='invalid_linkedin_url',
            ),
        ],
        help_text=_("LinkedIn profile URL (e.g., linkedin.com/in/username)."),
    )
    social_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^(https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(:[0-9]{1,5})?(/.*)?$',
                message=_("Enter a valid portfolio or personal website URL."),
                code='invalid_social_url',
            ),
        ],
        help_text=_("Portfolio or personal website URL."),
    )
    telegram_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^https://t\.me/[a-zA-Z][a-zA-Z0-9_]{4,31}$',
                message=_("Enter a valid Telegram URL (e.g., https://t.me/username)."),
                code='invalid_telegram_url',
            ),
        ],
        help_text=_("Telegram profile URL (e.g., https://t.me/username)."),
    )

    def __str__(self) -> str:
        return str(self.full_name)

    class Meta:
        verbose_name = "Candidate Profile"
        verbose_name_plural = "Candidate Profiles"
        indexes = [
            models.Index(fields=["candidate"]),
            models.Index(fields=["full_name"]),
        ]
