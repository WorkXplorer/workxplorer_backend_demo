import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import OAuthChallenge

logger = logging.getLogger(__name__)


class ChallengeInvalid(Exception):
    """Carries the failed check in .reason so the server log names it — the
    client only ever sees the opaque OAUTH_CHALLENGE_INVALID code."""

    def __init__(self, reason: str = "unknown"):
        self.reason = reason
        super().__init__(reason)


class ChallengeExpired(Exception):
    pass


class OAuthChallengeService:
    """
    One-shot nonce/state issued before a native Google/Apple sign-in. Only
    the digest is stored — the raw nonce/state only ever exist in the
    response to the app and in the provider SDK call, never persisted.
    """

    DEFAULT_TTL_SECONDS = 900

    @classmethod
    def ttl_seconds(cls) -> int:
        """Read per-request so OAUTH_CHALLENGE_TTL_SECONDS can be tuned without a code change."""
        return int(getattr(settings, "OAUTH_CHALLENGE_TTL_SECONDS", cls.DEFAULT_TTL_SECONDS))

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @classmethod
    def _matches(cls, presented: str, stored_digest: str) -> bool:
        """
        Two shapes count as a match:

        * the raw value we handed the app (its digest equals what we stored), and
        * the SHA-256 of that raw value, which is what a provider echoes back
          when the app follows Apple's documented hashed-nonce flow (send
          SHA256(rawNonce) to the SDK). Since we store exactly that hex digest,
          the echoed claim is compared to it directly.

        Both prove the caller held the raw nonce, which is the point of the check.
        """
        if secrets.compare_digest(cls._digest(presented), stored_digest):
            return True
        try:
            return secrets.compare_digest(presented.lower(), stored_digest)
        except TypeError:
            # compare_digest rejects non-ASCII str — such a value can never be
            # a hex digest anyway.
            return False

    @classmethod
    def create(cls, provider: str, device_id: str):
        nonce = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        challenge = OAuthChallenge.objects.create(
            provider=provider,
            device_id=device_id,
            nonce_digest=cls._digest(nonce),
            state_digest=cls._digest(state),
            expires_at=timezone.now() + timedelta(seconds=cls.ttl_seconds()),
        )
        return challenge, nonce, state

    @classmethod
    def consume(cls, challenge_id: str, provider: str, device_id: str, nonce: str = None, state: str = None) -> OAuthChallenge:
        """
        Atomically validates and marks the challenge consumed. Raises
        ChallengeInvalid (wrong/unknown/already-used/mismatched) or
        ChallengeExpired.
        """
        with transaction.atomic():
            try:
                challenge = OAuthChallenge.objects.select_for_update().get(id=challenge_id)
            except (OAuthChallenge.DoesNotExist, ValueError, TypeError):
                raise ChallengeInvalid("unknown_challenge_id")

            if challenge.consumed_at is not None:
                raise ChallengeInvalid("already_consumed")
            if challenge.provider != provider:
                raise ChallengeInvalid("provider_mismatch")
            if challenge.device_id != device_id:
                raise ChallengeInvalid("device_id_mismatch")
            if challenge.expires_at <= timezone.now():
                raise ChallengeExpired()
            if nonce is not None and not cls._matches(nonce, challenge.nonce_digest):
                raise ChallengeInvalid("nonce_mismatch")
            if state is not None and not cls._matches(state, challenge.state_digest):
                raise ChallengeInvalid("state_mismatch")

            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at"])

        return challenge
