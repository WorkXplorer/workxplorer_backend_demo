import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken as JWTRefreshToken

from ..models.consent import UserConsent
from ..models.mobile_session import MobileSession

logger = logging.getLogger(__name__)


class AccountDeletionService:
    """
    Service that permanently deletes a candidate account.

    Everything owned by the user (profile, resumes, applications, saved
    vacancies, subscriptions, mobile sessions, ...) is removed by database
    cascade. Consent records are the one exception: they are immutable legal
    records, so instead of being deleted they are flagged as belonging to a
    deleted consenter.
    """

    @staticmethod
    def _detach_consents(user):
        """
        Mark the user's consent records as orphaned before the user row goes
        away. UserConsent uses a generic relation, so nothing cascades — the
        records would otherwise point at a non-existent object.
        """
        content_type = ContentType.objects.get_for_model(user.__class__)
        consents = UserConsent.objects.filter(
            content_type=content_type, object_id=str(user.pk)
        )
        consents.update(consenter_email=user.email, consenter_deleted=True)

    @staticmethod
    def _revoke_sessions(user, refresh_token=None):
        """
        Revoke everything that could still authenticate as this user.

        Mobile sessions and outstanding JWTs are removed by cascade when the
        user row is deleted; blacklisting the current web refresh token first
        makes the revocation explicit and covers the (short) window before the
        transaction commits.
        """
        if refresh_token:
            try:
                JWTRefreshToken(refresh_token).blacklist()
            except TokenError:
                logger.warning("Invalid refresh token during account deletion")

        MobileSession.objects.filter(user=user).update(
            status=MobileSession.Status.REVOKED
        )

    @classmethod
    @transaction.atomic
    def delete_account(cls, user, refresh_token=None, reason=""):
        """
        Permanently delete the given user's account.

        Args:
            user: the CustomUser (candidate) to delete.
            refresh_token: the caller's refresh token, blacklisted if present.
            reason: optional free-text reason, logged for product analytics.
        """
        user_id = str(user.pk)
        email = user.email

        cls._revoke_sessions(user, refresh_token=refresh_token)
        cls._detach_consents(user)
        user.delete()

        logger.info(
            "Account deleted: user_id=%s email=%s reason=%s",
            user_id,
            email,
            reason or "not provided",
        )
