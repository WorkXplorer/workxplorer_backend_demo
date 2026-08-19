from django.db import models
from django.utils.translation import gettext_lazy as _

from utils.fields import UUIDField


class MobileSession(models.Model):
    """
    One row per app install/device. A session IS a refresh-token family:
    RefreshToken rows chained under it via parent/replaced_by represent that
    family's rotation history, so "revoke this session" and "revoke this
    token family" are the same operation.
    """

    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    class AuthMethod(models.TextChoices):
        PASSWORD = "password", "Password"
        GOOGLE = "google", "Google"
        APPLE = "apple", "Apple"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"

    id = UUIDField(primary_key=True, version=7, editable=False)
    user = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="mobile_sessions",
    )
    device_id = models.CharField(max_length=100, help_text="Client-generated installation UUID.")
    platform = models.CharField(max_length=10, choices=Platform.choices)
    app_version = models.CharField(max_length=20, null=True, blank=True)
    build_number = models.CharField(max_length=20, null=True, blank=True)
    device_name = models.CharField(max_length=100, null=True, blank=True)
    auth_method = models.CharField(max_length=10, choices=AuthMethod.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    idle_expires_at = models.DateTimeField(
        help_text="Reset to now + idle TTL on every successful refresh."
    )
    absolute_expires_at = models.DateTimeField(
        help_text="Hard cap from session creation — never extended."
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        verbose_name = _("mobile session")
        verbose_name_plural = _("mobile sessions")
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["idle_expires_at"]),
            models.Index(fields=["absolute_expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.device_id}:{self.platform}"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class RefreshToken(models.Model):
    """
    An opaque refresh token is never stored raw — only its HMAC digest
    (RefreshTokenService._digest). used_at set = rotated away; presenting a
    used token again is a replay and revokes the whole session (see
    RefreshTokenService.rotate).
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    session = models.ForeignKey(
        MobileSession, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    token_digest = models.CharField(max_length=64, unique=True)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("refresh token")
        verbose_name_plural = _("refresh tokens")
        indexes = [
            models.Index(fields=["session", "used_at"]),
        ]

    def __str__(self) -> str:
        return str(self.id)


class OAuthChallenge(models.Model):
    """
    One-shot nonce/state issued before a native Google/Apple sign-in, so the
    identity/authorization-code exchange can be tied back to a specific
    device+provider request and can't be replayed.
    """

    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        APPLE = "apple", "Apple"

    id = UUIDField(primary_key=True, version=7, editable=False)
    provider = models.CharField(max_length=10, choices=Provider.choices)
    device_id = models.CharField(max_length=100)
    nonce_digest = models.CharField(max_length=64)
    state_digest = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("OAuth challenge")
        verbose_name_plural = _("OAuth challenges")
        indexes = [
            models.Index(fields=["expires_at"]),
        ]
