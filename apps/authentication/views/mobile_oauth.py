import logging

from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from rest_framework import serializers
from rest_framework.views import APIView

from apps.authentication.models import MobileSession, SocialIdentity
from apps.authentication.permissions import IsMobileAppClient
from apps.authentication.serializers.device import DeviceSerializer
from apps.authentication.services.apple_client import (
    AppleClient,
    AppleNotConfigured,
    AppleUnavailable,
    InvalidAppleCode,
    InvalidAppleToken,
)
from apps.authentication.services.google_verifier import (
    GoogleUnavailable,
    InvalidGoogleToken,
    verify_google_id_token,
)
from apps.authentication.services.mobile_response import build_session_response_data
from apps.authentication.services.mobile_session_service import MobileSessionService
from apps.authentication.services.oauth_challenge_service import (
    ChallengeExpired,
    ChallengeInvalid,
    OAuthChallengeService,
)
from apps.authentication.services.provider_token_crypto import (
    ProviderTokenEncryptionNotConfigured,
    encrypt_provider_token,
)
from apps.authentication.services.social_account_service import (
    AccountLinkRequired,
    SocialAccountResolutionService,
    WrongUserTypeConflict,
)
from apps.authentication.views.mobile_auth import _post_login_bookkeeping
from core.responses import APIResponse

logger = logging.getLogger(__name__)


@extend_schema(
    summary="Create an OAuth challenge",
    description="One-time nonce/state to pass into the native Google/Apple SDK before calling "
                "/auth/mobile/google/ or /auth/mobile/apple/. Requires X-Mobile-App-Key. Single "
                "use; the lifetime is returned as expires_in (15 minutes by default, set by "
                "OAUTH_CHALLENGE_TTL_SECONDS).",
    request=inline_serializer(
        "OAuthChallengeRequest",
        fields={"provider": serializers.ChoiceField(choices=["google", "apple"]), "device_id": serializers.CharField()},
    ),
    responses={201: OpenApiResponse(description="challenge_id/nonce/state issued.")},
)
class MobileOAuthChallengeView(APIView):
    permission_classes = [IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        provider = request.data.get("provider")
        device_id = request.data.get("device_id")

        if provider not in ("google", "apple") or not device_id:
            return APIResponse.validation_error(message=_("provider must be 'google' or 'apple'; device_id is required."))

        challenge, nonce, state = OAuthChallengeService.create(provider, device_id)
        return APIResponse.success(
            data={
                "challenge_id": str(challenge.id),
                "nonce": nonce,
                "state": state,
                "expires_in": OAuthChallengeService.ttl_seconds(),
            },
            message=_("Challenge created."),
            status_code=201,
        )


def _apple_misconfigured_response():
    """
    A missing/broken APPLE_* secret is an operator problem, not the app's —
    answer 503 with a stable code instead of leaking a generic 500, and leave
    the specifics (already logged by AppleClient) out of the response body.
    """
    return APIResponse.error(
        message=_("Apple sign-in is temporarily unavailable."),
        code="APPLE_NOT_CONFIGURED",
        status_code=503,
    )


def _challenge_error_response(exc, *, provider: str, challenge_id: str, device_id: str):
    """
    The client keeps getting one opaque code per outcome — which check failed
    is a server-side detail — but the log names it, so a rejection in the wild
    (wrong device_id? reused challenge? hashed nonce?) is diagnosable without
    reproducing it on a device.
    """
    if isinstance(exc, ChallengeExpired):
        logger.info(
            "OAuth challenge expired: provider=%s challenge_id=%s device_id=%s", provider, challenge_id, device_id
        )
        return APIResponse.error(message=_("Challenge expired."), code="OAUTH_CHALLENGE_EXPIRED", status_code=400)

    logger.warning(
        "OAuth challenge rejected (%s): provider=%s challenge_id=%s device_id=%s",
        getattr(exc, "reason", "unknown"),
        provider,
        challenge_id,
        device_id,
    )
    return APIResponse.error(message=_("Challenge invalid."), code="OAUTH_CHALLENGE_INVALID", status_code=400)


@extend_schema(
    summary="Log in / register with Google (mobile app, candidate only)",
    description="Verifies a native Google ID token, resolves/links/creates a candidate account, "
                "and issues a MobileSession. Requires X-Mobile-App-Key.",
    request=inline_serializer(
        "MobileGoogleRequest",
        fields={
            "challenge_id": serializers.CharField(),
            "id_token": serializers.CharField(),
            "device": inline_serializer(
                "MobileGoogleDevice",
                fields={"device_id": serializers.CharField(), "platform": serializers.ChoiceField(choices=["ios", "android"])},
            ),
        },
    ),
    responses={
        200: OpenApiResponse(description="Existing user — session issued."),
        201: OpenApiResponse(description="New candidate created — session issued."),
    },
)
class MobileGoogleView(APIView):
    permission_classes = [IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        challenge_id = request.data.get("challenge_id")
        id_token_str = request.data.get("id_token")

        if not challenge_id or not id_token_str:
            return APIResponse.validation_error(message=_("challenge_id and id_token are required."))

        device_serializer = DeviceSerializer(data=request.data.get("device") or {})
        if not device_serializer.is_valid():
            return APIResponse.validation_error(field_errors=device_serializer.errors)
        device = device_serializer.validated_data

        try:
            google_claims = verify_google_id_token(id_token_str)
        except InvalidGoogleToken:
            return APIResponse.error(message=_("Invalid Google token."), code="INVALID_GOOGLE_TOKEN", status_code=401)
        except GoogleUnavailable:
            return APIResponse.error(
                message=_("Could not reach Google. Please try again."),
                code="GOOGLE_UNAVAILABLE",
                status_code=503,
            )

        try:
            OAuthChallengeService.consume(
                challenge_id, "google", device["device_id"], nonce=google_claims["nonce"]
            )
        except (ChallengeExpired, ChallengeInvalid) as exc:
            return _challenge_error_response(
                exc, provider="google", challenge_id=challenge_id, device_id=device["device_id"]
            )

        try:
            user, created = SocialAccountResolutionService.resolve_or_create_candidate(
                provider=SocialIdentity.Provider.GOOGLE,
                subject=google_claims["subject"],
                email=google_claims["email"],
                email_verified=google_claims["email_verified"],
                request=request,
            )
        except WrongUserTypeConflict:
            return APIResponse.error(message=_("This Google account is linked to a non-candidate account."), code="WRONG_USER_TYPE", status_code=403)
        except AccountLinkRequired:
            return APIResponse.error(message=_("Sign in with your password once to link this Google account."), code="ACCOUNT_LINK_REQUIRED", status_code=409)

        if not user.is_active:
            return APIResponse.error(message=_("This account has been deactivated."), code="ACCOUNT_DISABLED", status_code=403)

        SocialIdentity.objects.filter(user=user, provider=SocialIdentity.Provider.GOOGLE).update(last_login_at=timezone.now())
        _post_login_bookkeeping(request, user)

        bundle = MobileSessionService.create_session(user, device, MobileSession.AuthMethod.GOOGLE)
        return APIResponse.success(
            data=build_session_response_data(user, bundle),
            message=_("Login successful"),
            status_code=201 if created else 200,
        )


@extend_schema(
    summary="Log in / register with Apple (mobile app, iOS only, candidate only)",
    description="Verifies a native Sign in with Apple identity token, exchanges the authorization "
                "code, resolves/links/creates a candidate account, and issues a MobileSession. "
                "Requires X-Mobile-App-Key.",
    request=inline_serializer(
        "MobileAppleRequest",
        fields={
            "challenge_id": serializers.CharField(),
            "state": serializers.CharField(),
            "identity_token": serializers.CharField(),
            "authorization_code": serializers.CharField(),
            "device": inline_serializer(
                "MobileAppleDevice",
                fields={"device_id": serializers.CharField(), "platform": serializers.ChoiceField(choices=["ios"])},
            ),
        },
    ),
    responses={
        200: OpenApiResponse(description="Existing user — session issued."),
        201: OpenApiResponse(description="New candidate created — session issued."),
    },
)
class MobileAppleView(APIView):
    permission_classes = [IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        challenge_id = request.data.get("challenge_id")
        state = request.data.get("state")
        identity_token = request.data.get("identity_token")
        authorization_code = request.data.get("authorization_code")

        if not all([challenge_id, state, identity_token, authorization_code]):
            return APIResponse.validation_error(
                message=_("challenge_id, state, identity_token and authorization_code are required.")
            )

        device_serializer = DeviceSerializer(data=request.data.get("device") or {})
        if not device_serializer.is_valid():
            return APIResponse.validation_error(field_errors=device_serializer.errors)
        device = device_serializer.validated_data

        if device["platform"] != "ios":
            return APIResponse.error(message=_("Apple sign-in is only available on iOS."), code="WRONG_USER_TYPE", status_code=400)

        try:
            apple_claims = AppleClient.verify_identity_token(identity_token)
        except InvalidAppleToken:
            return APIResponse.error(message=_("Invalid Apple token."), code="INVALID_APPLE_TOKEN", status_code=401)
        except AppleNotConfigured:
            return _apple_misconfigured_response()
        except AppleUnavailable:
            return APIResponse.error(
                message=_("Could not reach Apple. Please try again."),
                code="APPLE_UNAVAILABLE",
                status_code=503,
            )

        try:
            OAuthChallengeService.consume(
                challenge_id, "apple", device["device_id"], nonce=apple_claims["nonce"], state=state
            )
        except (ChallengeExpired, ChallengeInvalid) as exc:
            return _challenge_error_response(
                exc, provider="apple", challenge_id=challenge_id, device_id=device["device_id"]
            )

        try:
            token_response = AppleClient.exchange_authorization_code(
                authorization_code, expected_subject=apple_claims["subject"]
            )
        except InvalidAppleCode:
            return APIResponse.error(message=_("Invalid or expired Apple authorization code."), code="INVALID_APPLE_CODE", status_code=401)
        except AppleNotConfigured:
            return _apple_misconfigured_response()

        if not apple_claims["email"]:
            # No email on an unknown sub means the backend can't safely bootstrap
            # a first registration — known accounts always have a stored email.
            existing = SocialIdentity.objects.filter(
                provider=SocialIdentity.Provider.APPLE, subject=apple_claims["subject"]
            ).exists()
            if not existing:
                return APIResponse.error(
                    message=_("Apple did not provide an email for this first sign-in."),
                    code="APPLE_EMAIL_REQUIRED",
                    status_code=422,
                )

        try:
            user, created = SocialAccountResolutionService.resolve_or_create_candidate(
                provider=SocialIdentity.Provider.APPLE,
                subject=apple_claims["subject"],
                email=apple_claims["email"],
                email_verified=apple_claims["email_verified"],
                request=request,
            )
        except WrongUserTypeConflict:
            return APIResponse.error(message=_("This Apple account is linked to a non-candidate account."), code="WRONG_USER_TYPE", status_code=403)
        except AccountLinkRequired:
            return APIResponse.error(message=_("Sign in with your password once to link this Apple account."), code="ACCOUNT_LINK_REQUIRED", status_code=409)

        if not user.is_active:
            return APIResponse.error(message=_("This account has been deactivated."), code="ACCOUNT_DISABLED", status_code=403)

        update_fields = {"last_login_at": timezone.now()}
        apple_refresh_token = token_response.get("refresh_token")
        if apple_refresh_token:
            try:
                update_fields["apple_refresh_token_ciphertext"] = encrypt_provider_token(apple_refresh_token)
            except (ProviderTokenEncryptionNotConfigured, ValueError, TypeError) as exc:
                # Still fails closed — the refresh token is never stored in the
                # clear — but as a diagnosable 503 rather than a generic 500.
                logger.error("Apple: could not encrypt the provider refresh token: %s", exc)
                return _apple_misconfigured_response()
        SocialIdentity.objects.filter(user=user, provider=SocialIdentity.Provider.APPLE).update(**update_fields)

        _post_login_bookkeeping(request, user)

        bundle = MobileSessionService.create_session(user, device, MobileSession.AuthMethod.APPLE)
        return APIResponse.success(
            data=build_session_response_data(user, bundle),
            message=_("Login successful"),
            status_code=201 if created else 200,
        )
