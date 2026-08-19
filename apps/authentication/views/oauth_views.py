import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from rest_framework.permissions import AllowAny
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample, inline_serializer

from core.responses import APIResponse
from apps.authentication.models.candidate import Candidate
from apps.authentication.services.authentication import activate_request_timezone
from apps.authentication.services.consent_service import ConsentService

logger = logging.getLogger(__name__)

User = get_user_model()


class GoogleOAuthCandidateView(APIView):
    """
    POST /auth/google/

    Accepts a Google ID token (credential) from the frontend (e.g. obtained
    via the Google Identity Services one-tap or sign-in button), verifies it
    server-side, then either:
      - logs in an existing Candidate account linked to that email, or
      - creates a new Candidate account and auto-records consent.

    Returns JWT access/refresh tokens as httpOnly cookies, matching the
    existing CookieTokenObtainPairView behaviour.

    Request body:
        {
            "credential": "<google-id-token-string>"
        }

    Responses:
        200 - success; cookies set
        400 - missing/invalid credential or unverified email
        401 - Google token verification failed
        403 - email already registered as a non-candidate user
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Log in / register with Google (candidate)",
        description="Accepts a Google ID token (credential) from the frontend, verifies it server-side, "
                    "then either logs in an existing candidate or creates a new one. "
                    "Returns JWT tokens as httpOnly cookies, matching the standard CookieTokenObtainPairView behaviour.",
        request=inline_serializer(
            "GoogleOAuthRequest",
            fields={
                "credential": serializers.CharField(
                    write_only=True,
                    help_text="Google ID token string obtained from Google Identity Services",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "GoogleOAuthSuccess",
                    fields={
                        "user": inline_serializer(
                            "GoogleOAuthUser",
                            fields={"email": serializers.EmailField()},
                        ),
                    },
                ),
                description="Login/registration successful. httpOnly cookies (access_token, refresh_token) are set.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {"user": {"email": "user@gmail.com"}},
                            "message": "Login successful",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                ],
            ),
            400: OpenApiResponse(
                description="Missing credential, unverified Google email, or email already registered as non-candidate",
                examples=[
                    OpenApiExample(
                        "Missing Credential",
                        value={
                            "success": False,
                            "error": {"code": "MISSING_CREDENTIAL", "message": "Google credential is required."},
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Email Not Verified",
                        value={
                            "success": False,
                            "error": {"code": "EMAIL_NOT_VERIFIED", "message": "Google account email is not verified."},
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Google ID token verification failed (invalid or expired)",
                examples=[
                    OpenApiExample(
                        "Invalid Token",
                        value={
                            "success": False,
                            "error": {"code": "INVALID_GOOGLE_TOKEN", "message": "Invalid or expired Google credential."},
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["401"],
                    ),
                ],
            ),
            403: OpenApiResponse(
                description="Email belongs to a non-candidate account or account is deactivated",
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        credential = request.data.get("credential")
        if not credential:
            return APIResponse.error(
                message=_("Google credential is required."),
                code="MISSING_CREDENTIAL",
                status_code=400,
            )

        # --- Verify Google ID token ---
        try:
            id_info = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                settings.APP_CLIENT_ID,
            )
        except ValueError as exc:
            logger.warning("Google ID token verification failed: %s", exc)
            return APIResponse.error(
                message=_("Invalid or expired Google credential."),
                code="INVALID_GOOGLE_TOKEN",
                status_code=401,
            )

        if not id_info.get("email_verified"):
            return APIResponse.error(
                message=_("Google account email is not verified."),
                code="EMAIL_NOT_VERIFIED",
                status_code=400,
            )

        email = id_info["email"]

        # --- Find or create user ---
        user = User.objects.filter(email=email).first()

        if user is not None:
            # Existing user: must be a candidate
            if not hasattr(user, "candidate"):
                return APIResponse.error(
                    message=_(
                        "This Google account is linked to a non-candidate account. "
                        "Please log in with your email and password."
                    ),
                    code="WRONG_USER_TYPE",
                    status_code=403,
                )
            if not user.is_active:
                return APIResponse.error(
                    message=_("This account has been deactivated."),
                    code="ACCOUNT_INACTIVE",
                    status_code=403,
                )
        else:
            # New user: create as Candidate
            try:
                with transaction.atomic():
                    user = Candidate(
                        email=email,
                        is_active=True,
                        is_candidate=True,
                    )
                    user.set_unusable_password()
                    user.save()

                    # Record consent (gracefully skip if no active configs)
                    try:
                        ConsentService.create_consents_for_entity(
                            consenter=user,
                            entity_type="candidate",
                            ip_address=ConsentService.get_client_ip(request),
                            user_agent=request.META.get("HTTP_USER_AGENT", ""),
                            request=request,
                        )
                    except ValueError as exc:
                        logger.warning(
                            "Could not create consent records for OAuth candidate %s: %s",
                            email,
                            exc,
                        )
            except Exception as exc:
                logger.exception(
                    "Unexpected error creating OAuth candidate %s: %s", email, exc
                )
                return APIResponse.server_error(
                    message=_("Failed to create account. Please try again later.")
                )

        # Activate timezone from X-Timezone header (OAuth login has no JWT yet)
        activate_request_timezone(request, user)

        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = APIResponse.success(
            data={"user": {"email": user.email}},
            message=_("Login successful"),
        )
        self._set_auth_cookies(response, access_token, refresh_token)
        return response

    def _set_auth_cookies(self, response, access_token, refresh_token):
        """Set httpOnly cookies matching the standard CookieTokenObtainPairView pattern."""
        access_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        response.set_cookie(
            "access_token",
            access_token,
            max_age=int(access_lifetime.total_seconds()),
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )
        response.set_cookie(
            "refresh_token",
            refresh_token,
            max_age=None,  # session cookie
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )
