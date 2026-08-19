from django.db import models
from django.utils.translation import gettext_lazy as _

from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class SocialIdentity(AbstractBaseModel):
    """
    Links a CustomUser to a Google/Apple identity. (provider, subject) is the
    only trustworthy, stable identifier for a provider account — never email,
    which can change ownership.
    """

    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        APPLE = "apple", "Apple"

    id = UUIDField(primary_key=True, version=7, editable=False)
    user = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="social_identities",
    )
    provider = models.CharField(max_length=10, choices=Provider.choices)
    subject = models.CharField(
        max_length=255,
        help_text="Provider's stable, opaque user identifier (Google 'sub' / Apple 'sub').",
    )
    email_at_link = models.EmailField(
        null=True, blank=True,
        help_text="Email the provider reported at link time — display only, never an identity key.",
    )
    email_verified = models.BooleanField(default=False)
    apple_refresh_token_ciphertext = models.TextField(
        null=True, blank=True,
        help_text="Envelope-encrypted Apple provider refresh token (Apple identities only). "
                   "Used only for status checks and revocation on account deletion.",
    )
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("social identity")
        verbose_name_plural = _("social identities")
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="unique_provider_subject"),
            models.UniqueConstraint(fields=["user", "provider"], name="unique_user_provider"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.subject}"
