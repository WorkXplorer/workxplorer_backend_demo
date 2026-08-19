import logging
from django.contrib.auth import authenticate
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer

from core.responses import APIResponse
from apps.authentication.models import MobileSession
from apps.authentication.permissions import IsMobileAppClient
from apps.authentication.serializers.device import DeviceSerializer
from apps.authentication.services.authentication import activate_request_timezone
from apps.authentication.services.mobile_session_service import (
    InvalidRefreshToken,
    MobileSessionService,
    RefreshTokenReused,
    SessionExpired,
    SessionRevoked,
)
from apps.authentication.services.mobile_response import (
    build_refresh_response_data,
    build_session_response_data,
)
from apps.general.services.language_cache import LanguageCacheService
from utils.language import get_request_language

logger = logging.getLogger(__name__)


def _post_login_bookkeeping(request, user):
    """Shared with the web login flow's intent: update last_login/language,
    attach any pending anonymous quiz result. Only for candidates."""
    activate_request_timezone(request, user)

    user.last_login = timezone.now()
    update_fields = ["last_login"]
    if not user.preferred_language:
        user.preferred_language = get_request_language()
        update_fields.append("preferred_language")
    user.save(update_fields=update_fields)
    LanguageCacheService.set_user_language(str(user.id), user.preferred_language)

    try:
        from apps.authentication.models import Candidate as _Candidate
        from apps.quiz.services.pending_quiz_service import attach_pending_to_candidate
        candidate = _Candidate.objects.filter(pk=user.pk).first()
        if candidate:
            attach_pending_to_candidate(candidate)
    except Exception:
        logger.exception("Failed to attach pending quiz result after mobile login for user %s", user.pk)


@extend_schema(
    summary="Log in (mobile app, password)",
    description="Candidate-only password login for the React Native app. Accepts 'email' or "
                "'phone' (a verified phone) plus 'password' and device metadata. Requires the "
                "X-Mobile-App-Key header. Creates a new MobileSession for this device and returns "
                "tokens in the response body.",
    request=inline_serializer(
        "MobileLoginRequest",
        fields={
            "email": serializers.EmailField(required=False),
            "phone": serializers.CharField(required=False),
            "password": serializers.CharField(write_only=True),
            "device": inline_serializer(
                "MobileLoginDevice",
                fields={
                    "device_id": serializers.CharField(),
                    "platform": serializers.ChoiceField(choices=["ios", "android"]),
                    "app_version": serializers.CharField(required=False),
                    "build_number": serializers.CharField(required=False),
                    "device_name": serializers.CharField(required=False),
                },
            ),
        },
    ),
    responses={
        200: OpenApiResponse(description="Login successful — access/refresh tokens in the response body."),
        401: OpenApiResponse(description="INVALID_CREDENTIALS"),
        403: OpenApiResponse(description="WRONG_USER_TYPE / ACCOUNT_DISABLED"),
    },
)
class MobileLoginView(APIView):
    permission_classes = [IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        identifier = request.data.get("email") or request.data.get("phone")
        password = request.data.get("password")

        if not identifier or not password:
            return APIResponse.error(
                message=_("Invalid credentials"), code="INVALID_CREDENTIALS", status_code=400,
            )

        device_serializer = DeviceSerializer(data=request.data.get("device") or {})
        if not device_serializer.is_valid():
            return APIResponse.validation_error(field_errors=device_serializer.errors)

        # Note: role is never taken from the client — only resolved server-side below.
        user = authenticate(request, email=identifier, password=password)
        if user is None:
            return APIResponse.error(
                message=_("Invalid credentials"), code="INVALID_CREDENTIALS", status_code=401,
            )

        if not hasattr(user, "candidate"):
            return APIResponse.error(
                message=_("Only candidate accounts can sign in to the mobile app."),
                code="WRONG_USER_TYPE",
                status_code=403,
            )

        if not user.is_active:
            return APIResponse.error(
                message=_("This account has been deactivated."), code="ACCOUNT_DISABLED", status_code=403,
            )

        _post_login_bookkeeping(request, user)

        bundle = MobileSessionService.create_session(
            user, device_serializer.validated_data, MobileSession.AuthMethod.PASSWORD
        )
        return APIResponse.success(
            data=build_session_response_data(user, bundle), message=_("Login successful")
        )


@extend_schema(
    summary="Refresh mobile session",
    description="Rotates the refresh token and issues a new access/refresh pair. Requires the "
                "X-Mobile-App-Key header. A used/replaced refresh token is treated as a replay "
                "and revokes the whole session.",
    request=inline_serializer("MobileRefreshRequest", fields={"refresh_token": serializers.CharField()}),
    responses={
        200: OpenApiResponse(description="New access/refresh pair."),
        401: OpenApiResponse(description="INVALID_REFRESH_TOKEN / SESSION_EXPIRED / SESSION_REVOKED / REFRESH_TOKEN_REUSED"),
    },
)
class MobileRefreshView(APIView):
    permission_classes = [IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        raw_refresh_token = request.data.get("refresh_token")
        if not raw_refresh_token:
            return APIResponse.unauthorized(message=_("Refresh token not found in request body"))

        try:
            bundle = MobileSessionService.rotate(raw_refresh_token)
        except InvalidRefreshToken:
            return APIResponse.error(message=_("Invalid refresh token"), code="INVALID_REFRESH_TOKEN", status_code=401)
        except SessionExpired:
            return APIResponse.error(message=_("Session expired"), code="SESSION_EXPIRED", status_code=401)
        except SessionRevoked:
            return APIResponse.error(message=_("Session revoked"), code="SESSION_REVOKED", status_code=401)
        except RefreshTokenReused:
            return APIResponse.error(
                message=_("This refresh token was already used — session revoked."),
                code="REFRESH_TOKEN_REUSED",
                status_code=401,
            )

        return APIResponse.success(
            data=build_refresh_response_data(bundle), message=_("Token refreshed successfully")
        )


@extend_schema(
    summary="Log out (current device)",
    description="Revokes only the session tied to the supplied refresh token. Other devices stay "
                "signed in. Idempotent — always succeeds, even for an unknown/already-revoked token.",
    request=inline_serializer("MobileLogoutRequest", fields={"refresh_token": serializers.CharField(required=False)}),
    responses={204: None},
)
class MobileLogoutView(APIView):
    permission_classes = [IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        raw_refresh_token = request.data.get("refresh_token")
        if raw_refresh_token:
            MobileSessionService.revoke_by_refresh_token(raw_refresh_token, reason="logout")
        return APIResponse.no_content(message=_("Successfully logged out"))


@extend_schema(
    summary="Log out (all devices)",
    description="Revokes every MobileSession for the authenticated user, including the one making "
                "this request. Requires Authorization: Bearer <access_token>.",
    request=None,
    responses={204: None},
)
class MobileLogoutAllView(APIView):
    permission_classes = [IsAuthenticated, IsMobileAppClient]

    def post(self, request, *args, **kwargs):
        MobileSessionService.revoke_all_sessions(request.user, reason="logout_all")

        # Revoking sessions has to reach the chat gateway too, or a socket
        # opened before the revocation keeps delivering messages.
        from apps.conversations.realtime import disconnect_users

        disconnect_users([request.user.id], reason="logout_all")

        return APIResponse.no_content(message=_("All sessions revoked"))
