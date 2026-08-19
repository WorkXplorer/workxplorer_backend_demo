import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import MobileSession, RefreshToken


class InvalidRefreshToken(Exception):
    pass


class SessionExpired(Exception):
    pass


class SessionRevoked(Exception):
    pass


class RefreshTokenReused(Exception):
    """Raised when a used/replaced refresh token is presented again — the
    whole session has already been revoked by the time this is raised."""


@dataclass
class SessionBundle:
    session: MobileSession
    access_token: str
    refresh_token: str


class MobileSessionService:
    """
    Owns the mobile session lifecycle: one MobileSession per device install,
    backed by a chain of opaque RefreshToken rows (a session IS its token
    family — see MobileSession's docstring). Refresh tokens are never stored
    raw, only as an HMAC-SHA256 digest keyed by AUTH_REFRESH_PEPPER.
    """

    @staticmethod
    def _generate_opaque_token() -> str:
        return secrets.token_urlsafe(32)  # 256 bits of entropy

    @staticmethod
    def _digest(raw_token: str) -> str:
        return hmac.new(
            settings.AUTH_REFRESH_PEPPER.encode("utf-8"),
            raw_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def issue_access_token(user, session: MobileSession) -> str:
        token = AccessToken.for_user(user)
        token["sid"] = str(session.id)
        token["role"] = "candidate"
        return str(token)

    @classmethod
    def create_session(cls, user, device: dict, auth_method: str) -> SessionBundle:
        now = timezone.now()
        idle_ttl = timedelta(days=settings.MOBILE_SESSION_IDLE_TTL_DAYS)
        absolute_ttl = timedelta(days=settings.MOBILE_SESSION_ABSOLUTE_TTL_DAYS)

        with transaction.atomic():
            session = MobileSession.objects.create(
                user=user,
                device_id=device["device_id"],
                platform=device["platform"],
                app_version=device.get("app_version"),
                build_number=device.get("build_number"),
                device_name=device.get("device_name"),
                auth_method=auth_method,
                last_used_at=now,
                idle_expires_at=now + idle_ttl,
                absolute_expires_at=now + absolute_ttl,
            )
            raw_refresh = cls._generate_opaque_token()
            RefreshToken.objects.create(
                session=session,
                token_digest=cls._digest(raw_refresh),
                expires_at=session.idle_expires_at,
            )

        access_token = cls.issue_access_token(user, session)
        return SessionBundle(session=session, access_token=access_token, refresh_token=raw_refresh)

    @classmethod
    def rotate(cls, raw_refresh_token: str) -> SessionBundle:
        """
        Validates and rotates a refresh token. Raises InvalidRefreshToken,
        SessionExpired, SessionRevoked, or RefreshTokenReused — callers map
        these to the endpoint's stable error codes.

        The whole lookup -> validate -> mark-used -> create-child sequence
        runs in one transaction with SELECT ... FOR UPDATE on the token row,
        so two concurrent refreshes of the SAME token serialize: the first
        marks it used and rotates; the second, once it gets the lock, re-reads
        the now-used row and takes the replay path instead of forking the
        chain. Without the lock a race could bypass replay detection entirely.
        """
        digest_value = cls._digest(raw_refresh_token)
        now = timezone.now()
        bundle = None
        # Deferred outcome: for the expired/reused paths we must let the
        # revoke_session() writes COMMIT, so we record the outcome and raise
        # only after the atomic block — raising inside it would roll the
        # revoke back.
        outcome = "ok"

        with transaction.atomic():
            try:
                token = (
                    RefreshToken.objects
                    .select_for_update(of=("self",))
                    .select_related("session", "session__user")
                    .get(token_digest=digest_value)
                )
            except RefreshToken.DoesNotExist:
                # Nothing written — safe to raise inside the block.
                raise InvalidRefreshToken()

            session = token.session

            if session.status != MobileSession.Status.ACTIVE:
                raise SessionRevoked()  # nothing written yet — safe to raise here

            if session.absolute_expires_at <= now or session.idle_expires_at <= now:
                cls.revoke_session(session, "session_timeout", now=now)
                outcome = "expired"
            elif token.used_at is not None or token.revoked_at is not None:
                # A rotated-away token came back — either a lost-response retry
                # (client should have used the token it actually got back) or a
                # stolen token. Can't tell which, so treat as compromised: kill
                # the whole family.
                cls.revoke_session(session, "refresh_reuse_detected", now=now)
                outcome = "reused"
            else:
                token.used_at = now
                token.save(update_fields=["used_at"])

                session.idle_expires_at = now + timedelta(days=settings.MOBILE_SESSION_IDLE_TTL_DAYS)
                session.last_used_at = now
                session.save(update_fields=["idle_expires_at", "last_used_at"])

                new_raw_refresh = cls._generate_opaque_token()
                RefreshToken.objects.create(
                    session=session,
                    token_digest=cls._digest(new_raw_refresh),
                    parent=token,
                    expires_at=session.idle_expires_at,
                )
                access_token = cls.issue_access_token(session.user, session)
                bundle = SessionBundle(
                    session=session, access_token=access_token, refresh_token=new_raw_refresh
                )

        if outcome == "expired":
            raise SessionExpired()
        if outcome == "reused":
            raise RefreshTokenReused()
        return bundle

    @staticmethod
    def revoke_session(session: MobileSession, reason: str, now=None) -> None:
        now = now or timezone.now()
        session.status = MobileSession.Status.REVOKED
        session.revoked_at = now
        session.revoked_reason = reason
        session.save(update_fields=["status", "revoked_at", "revoked_reason"])
        RefreshToken.objects.filter(session=session, revoked_at__isnull=True).update(revoked_at=now)

    @classmethod
    def revoke_by_refresh_token(cls, raw_refresh_token: str, reason: str = "logout") -> None:
        """Idempotent: unknown/already-revoked tokens are a no-op, matching
        the logout endpoint's "always succeed" contract."""
        digest_value = cls._digest(raw_refresh_token)
        token = RefreshToken.objects.select_related("session").filter(token_digest=digest_value).first()
        if token and token.session.status == MobileSession.Status.ACTIVE:
            cls.revoke_session(token.session, reason)

    @classmethod
    def revoke_all_sessions(cls, user, reason: str = "logout_all") -> None:
        now = timezone.now()
        sessions = MobileSession.objects.filter(user=user, status=MobileSession.Status.ACTIVE)
        for session in sessions:
            cls.revoke_session(session, reason, now=now)

    @staticmethod
    def is_session_valid(session_id: str) -> bool:
        """Used by CookieJWTAuthentication to reject access tokens whose
        session was revoked (logout/logout-all) before the token's natural
        15-minute expiry."""
        now = timezone.now()
        return MobileSession.objects.filter(
            id=session_id,
            status=MobileSession.Status.ACTIVE,
            idle_expires_at__gt=now,
            absolute_expires_at__gt=now,
        ).exists()
