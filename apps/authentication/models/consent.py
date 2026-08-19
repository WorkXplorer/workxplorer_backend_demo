from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from utils.fields import UUIDField
from utils.abstract_model import AbstractBaseModel


class UserConsent(AbstractBaseModel):
    """
    Immutable record of consent to platform policies.
    
    Can track consent for:
    - Candidates (users)
    - Recruiters (users)
    - Companies (organizations)
    
    Records are write-once and cannot be modified or deleted.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)

    # Generic relation to support User OR Company
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.CharField(max_length=255)
    consenter = GenericForeignKey('content_type', 'object_id')

    # Reference to the consent configuration (optional for backwards compatibility)
    consent_config = models.ForeignKey(
        'authentication.ConsentConfiguration',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='consent_records',
        help_text="The configuration this consent was given under"
    )

    # Keep these fields for backwards compatibility and explicit tracking
    consent_type = models.CharField(
        max_length=50,
        help_text="Type of consent (e.g., 'terms_of_service', 'privacy_policy')"
    )
    version = models.CharField(
        max_length=20,
        help_text="Version of the policy agreed to (e.g., '1.0', '2.0')"
    )

    # Snapshot of who consented, kept readable after the consenter is deleted
    consenter_email = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Email (or name) of the consenter at the time of consent"
    )
    consenter_deleted = models.BooleanField(
        default=False,
        help_text="True when the consenting user or company no longer exists"
    )

    agreed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(
        help_text="IP address from which consent was given"
    )
    user_agent = models.TextField(
        blank=True,
        default='',
        help_text="Browser/device information"
    )

    # Optional: for consent withdrawal tracking
    withdrawn_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp if consent was withdrawn"
    )

    class Meta:
        verbose_name = "Consent Record"
        verbose_name_plural = "Consent Records"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['consent_type']),
            models.Index(fields=['agreed_at']),
        ]
        # Ensure one consent per entity per type per version
        unique_together = [['content_type', 'object_id', 'consent_type', 'version']]

    def delete(self, *args, **kwargs):
        """Prevent deletion of consent records"""
        raise ValueError("Consent records cannot be deleted")

    def __str__(self):
        consenter_str = ""
        if hasattr(self.consenter, 'email'):
            consenter_str = self.consenter.email
        elif hasattr(self.consenter, 'name'):
            consenter_str = self.consenter.name
        else:
            consenter_str = str(self.object_id)

        return f"{consenter_str} - {self.consent_type} v{self.version} at {self.agreed_at}"
