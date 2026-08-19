from django.db import models
from django.core.exceptions import ValidationError
from utils.fields import UUIDField


class ConsentConfiguration(models.Model):
    """
    Configuration for consent types required during registration.
    Defines which consents are required for which entity types.
    Only one active configuration per consent_type + entity_type combination.
    """

    class ConsentType(models.TextChoices):
        TERMS_OF_SERVICE = 'terms_of_service', 'Terms of Service'
        PRIVACY_POLICY = 'privacy_policy', 'Privacy Policy'
        DATA_PROCESSING = 'data_processing', 'Data Processing Agreement'
        COMPANY_TERMS = 'company_terms', 'Company Terms and Conditions'
        PUBLIC_OFFER = 'public_offer', 'Public Offer'

    class EntityType(models.TextChoices):
        CANDIDATE = 'candidate', 'Candidate'
        RECRUITER = 'recruiter', 'Recruiter'
        COMPANY = 'company', 'Company'

    id = UUIDField(primary_key=True, version=7, editable=False)

    consent_type = models.CharField(
        max_length=50,
        choices=ConsentType.choices,
        help_text="Type of consent (e.g., terms_of_service, privacy_policy)"
    )

    entity_type = models.CharField(
        max_length=20,
        choices=EntityType.choices,
        help_text="Which type of user this consent applies to"
    )

    version = models.CharField(
        max_length=20,
        help_text="Version of this consent (e.g., '1.0', '2.0')"
    )

    name = models.CharField(
        max_length=255,
        help_text="Display name for this consent",
        blank=True
    )

    name_uz = models.CharField(
        max_length=255,
        blank=True,
        help_text="Display name in Uzbek"
    )

    name_ru = models.CharField(
        max_length=255,
        blank=True,
        help_text="Display name in Russian"
    )

    name_en = models.CharField(
        max_length=255,
        blank=True,
        help_text="Display name in English"
    )

    description = models.TextField(
        blank=True,
        help_text="Description of what this consent covers"
    )

    description_uz = models.TextField(
        blank=True,
        help_text="Description in Uzbek"
    )

    description_ru = models.TextField(
        blank=True,
        help_text="Description in Russian"
    )

    description_en = models.TextField(
        blank=True,
        help_text="Description in English"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this consent configuration is currently active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Consent Configuration"
        verbose_name_plural = "Consent Configurations"
        indexes = [
            models.Index(fields=['consent_type', 'entity_type', 'is_active']),
            models.Index(fields=['is_active']),
        ]
        # Ensure uniqueness: only one active config per consent_type + entity_type
        constraints = [
            models.UniqueConstraint(
                fields=['consent_type', 'entity_type'],
                condition=models.Q(is_active=True),
                name='unique_active_consent_config'
            )
        ]

    def clean(self):
        """
        Validate that only one active configuration exists per consent_type + entity_type.
        """
        if self.is_active:
            # Check if another active config exists for same consent_type + entity_type
            existing = ConsentConfiguration.objects.filter(
                consent_type=self.consent_type,
                entity_type=self.entity_type,
                is_active=True
            ).exclude(pk=self.pk)

            if existing.exists():
                raise ValidationError(
                    f"An active configuration already exists for {self.get_consent_type_display()} "
                    f"for {self.get_entity_type_display()}. Please deactivate it first."
                )

    def save(self, *args, **kwargs):
        """Run validation before saving"""
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.name} v{self.version} for {self.get_entity_type_display()} ({status})"

    def get_localized_name(self, language='en'):
        """Get name in specified language, fallback to default"""
        if language == 'uz' and self.name_uz:
            return self.name_uz
        elif language == 'ru' and self.name_ru:
            return self.name_ru
        elif language == 'en' and self.name_en:
            return self.name_en
        return self.name

    def get_localized_description(self, language='en'):
        """Get description in specified language, fallback to default"""
        if language == 'uz' and self.description_uz:
            return self.description_uz
        elif language == 'ru' and self.description_ru:
            return self.description_ru
        elif language == 'en' and self.description_en:
            return self.description_en
        return self.description
