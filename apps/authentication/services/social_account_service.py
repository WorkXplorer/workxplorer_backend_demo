import logging

from django.db import transaction

from apps.authentication.models import Candidate, SocialIdentity
from apps.authentication.services.consent_service import ConsentService

logger = logging.getLogger(__name__)


class WrongUserTypeConflict(Exception):
    """Email belongs to an existing non-candidate account."""


class AccountLinkRequired(Exception):
    """Multiple/ambiguous accounts for this email — refuse to guess."""


class SocialAccountResolutionService:
    """
    Shared account resolution for provider sign-in (Google/Apple, web or
    mobile transport). Provider identity is always (provider, subject) —
    email is only used to find/create the local account, never as the
    identity key, per apps/authentication/README.md's OAuth section.

    Known simplification: any existing candidate account with a
    provider-verified email is auto-linked. The TZ additionally recommends
    withholding auto-link for external (non-Gmail) Google addresses lacking
    an `hd` (hosted domain) claim, since Google warns such addresses can
    change hands. Not implemented here — flagged as a follow-up hardening
    item, not a silent gap.
    """

    @classmethod
    def resolve_or_create_candidate(cls, provider: str, subject: str, email: str, email_verified: bool, request=None):
        """
        Returns (user, created). Raises WrongUserTypeConflict or
        AccountLinkRequired — callers translate those to their endpoint's
        error codes.
        """
        with transaction.atomic():
            identity = (
                SocialIdentity.objects.select_related("user")
                .filter(provider=provider, subject=subject)
                .first()
            )
            if identity is not None:
                user = identity.user
                if not hasattr(user, "candidate"):
                    raise WrongUserTypeConflict()
                return user, False

            if not email or not email_verified:
                # Apple's "no email on an unknown sub" case is handled by the
                # caller (APPLE_EMAIL_REQUIRED) before this is ever reached.
                raise AccountLinkRequired()

            from apps.authentication.models import CustomUser
            candidates = list(
                CustomUser.objects.select_for_update().filter(email__iexact=email)
            )

            if len(candidates) > 1:
                raise AccountLinkRequired()

            if len(candidates) == 1:
                user = candidates[0]
                if not hasattr(user, "candidate"):
                    raise WrongUserTypeConflict()
                SocialIdentity.objects.create(
                    user=user, provider=provider, subject=subject,
                    email_at_link=email, email_verified=email_verified,
                )
                return user, False

            user = Candidate(email=email, is_active=True, is_candidate=True)
            user.set_unusable_password()
            user.save()

            try:
                ConsentService.create_consents_for_entity(
                    consenter=user,
                    entity_type="candidate",
                    ip_address=ConsentService.get_client_ip(request) if request else None,
                    user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
                    request=request,
                )
            except ValueError as exc:
                logger.warning("Could not create consent records for %s social candidate %s: %s", provider, email, exc)

            SocialIdentity.objects.create(
                user=user, provider=provider, subject=subject,
                email_at_link=email, email_verified=email_verified,
            )
            return user, True
