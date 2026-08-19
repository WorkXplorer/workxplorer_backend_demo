import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from core.responses import APIResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from apps.authentication.serializers.token import EnvironmentAwareTokenSerializer
from apps.general.services.language_cache import LanguageCacheService
from utils.language import get_request_language
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample, inline_serializer
from rest_framework import serializers
from django.utils import timezone
from apps.authentication.services.authentication import activate_request_timezone

User = get_user_model()
logger = logging.getLogger(__name__)


class CookieTokenObtainPairView(TokenObtainPairView):
    """
    Custom token view that sets JWT tokens in httpOnly cookies.
    Supports "remember me" functionality for extended sessions.
    """

    permission_classes = [AllowAny]
    serializer_class = EnvironmentAwareTokenSerializer

    @extend_schema(
        summary="Log in (cookie-based JWT)",
        description="Authenticate with email + password, or verified phone + password "
                    "(send 'phone' instead of 'email'; the phone must already be verified via "
                    "/auth/phone/verify-otp/). On success, sets httpOnly cookies "
                    "(access_token, refresh_token). Tokens are NEVER returned in the response body. "
                    "Supports 'remember_me' for extended session lifetime.",
        request=inline_serializer(
            "LoginRequest",
            fields={
                "email": serializers.EmailField(required=False, help_text="User email address"),
                "phone": serializers.CharField(
                    required=False,
                    help_text="Verified phone number, e.g. +998901234567. Alternative to 'email'.",
                ),
                "password": serializers.CharField(write_only=True, help_text="User password"),
                "user_type": serializers.ChoiceField(
                    choices=[("candidate", "Candidate"), ("recruiter", "Recruiter")],
                    help_text="Type of user logging in",
                ),
                "remember_me": serializers.BooleanField(
                    required=False, default=False,
                    help_text="Extend refresh token lifetime (30 days vs session cookie)",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "LoginSuccessResponse",
                    fields={
                        "user": inline_serializer(
                            "LoginUserInfo",
                            fields={
                                "email": serializers.EmailField(),
                            },
                        ),
                        "company_is_active": serializers.BooleanField(required=False, default=None),
                    },
                ),
                description="Login successful. httpOnly cookies (access_token, refresh_token) are set. "
                            "company_is_active is only returned for recruiters.",
                examples=[
                    OpenApiExample(
                        "Candidate Login",
                        value={
                            "success": True,
                            "data": {"user": {"email": "candidate@example.com"}},
                            "message": "Login successful",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                    OpenApiExample(
                        "Recruiter Login",
                        value={
                            "success": True,
                            "data": {
                                "user": {"email": "recruiter@example.com"},
                                "company_is_active": True,
                            },
                            "message": "Login successful",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                ],
            ),
            400: OpenApiResponse(
                description="Invalid credentials or wrong user type",
                examples=[
                    OpenApiExample(
                        "Invalid Credentials",
                        value={
                            "success": False,
                            "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid credentials"},
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Wrong User Type",
                        value={
                            "success": False,
                            "error": {"code": "WRONG_USER_TYPE", "message": "Invalid credentials for student login"},
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["400"],
                    ),
                ],
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        user_type = request.data.get('user_type')
        remember_me = request.data.get('remember_me', False)

        # Authenticate via the serializer — this performs ONE user lookup
        # internally via authenticate() and stores the result as serializer.user.
        # We handle the serializer directly instead of calling super().post()
        # so we can reuse the fetched user object, avoiding two extra queries
        # (one pre-check + one re-fetch for post-login processing).
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError:
            # Validation errors from the serializer (missing fields, invalid
            # credentials) are returned as a generic 400 to avoid leaking
            # whether the email exists on the platform (user enumeration).
            return APIResponse.error(
                message=_("Invalid credentials"),
                code="INVALID_CREDENTIALS",
                status_code=400,
            )

        # Reuse the user object authenticated by the serializer — zero extra queries.
        user = serializer.user

        # Activate timezone from X-Timezone header (login request has no JWT yet)
        activate_request_timezone(request, user)

        # Validate user type matches login type
        if user_type == 'candidate' and not hasattr(user, 'candidate'):
            return APIResponse.error(
                message=_("Invalid credentials for student login"),
                code="WRONG_USER_TYPE",
            )

        if user_type == 'recruiter' and not hasattr(user, 'recruiter'):
            return APIResponse.error(
                message=_("Invalid credentials for recruiter login"),
                code="WRONG_USER_TYPE",
            )

        # Recruiter login is allowed even when the company is inactive or unapproved.
        # The frontend uses the company_is_active flag in the response (set below) to
        # restrict pages and features based on company approval status.

        # Update last login time and initialize language preference if not set
        user.last_login = timezone.now()
        update_fields = ['last_login']
        if not user.preferred_language:
            user.preferred_language = get_request_language()
            update_fields.append('preferred_language')
        user.save(update_fields=update_fields)
        LanguageCacheService.set_user_language(str(user.id), user.preferred_language)

        # Attach any pending anonymous quiz result (case 3 of the quiz flow)
        if user_type == "candidate":
            try:
                from apps.authentication.models import Candidate as _Candidate
                from apps.quiz.services.pending_quiz_service import attach_pending_to_candidate
                _candidate = _Candidate.objects.filter(pk=user.pk).first()
                if _candidate:
                    attach_pending_to_candidate(_candidate)
            except Exception:
                logger.exception(
                    "Failed to attach pending quiz result after login for user %s", user.pk
                )

        # Extract tokens from validated serializer data
        access_token = serializer.validated_data["access"]
        refresh_token_str = serializer.validated_data["refresh"]

        # Extend refresh token if remember_me is checked
        if remember_me:
            refresh_obj = RefreshToken(refresh_token_str)
            refresh_obj.set_exp(
                from_time=timezone.now(),
                lifetime=settings.SIMPLE_JWT["EXTENDED_REFRESH_TOKEN_LIFETIME"]
            )
            refresh_token_str = str(refresh_obj)

        # Create response without tokens in body
        # TEMPORARY: Include company_is_active flag so the frontend can restrict
        # pages/features when the company is still awaiting approval.
        response_data = {"user": {"email": user.email}}
        if user_type == 'recruiter' and hasattr(user, 'recruiter'):
            recruiter = user.recruiter
            response_data["company_is_active"] = (
                recruiter.company.is_active
                if recruiter.company
                else None
            )
        new_response = APIResponse.success(
            data=response_data,
            message=_("Login successful"),
        )

        # Set httpOnly cookies
        self._set_auth_cookies(new_response, access_token, refresh_token_str, remember_me)

        return new_response

    def _set_auth_cookies(self, response, access_token, refresh_token, remember_me=False):
        """
        Set httpOnly cookies for access and refresh tokens.
        
        Args:
            response: Response object to set cookies on
            access_token: JWT access token string
            refresh_token: JWT refresh token string (already extended if remember_me)
            remember_me: Whether to use extended cookie lifetime
        """
        # Access token cookie (always 15 minutes)
        access_token_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        response.set_cookie(
            "access_token",
            access_token,
            max_age=int(access_token_lifetime.total_seconds()),
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )

        # Refresh token cookie (explicit max_age if remember_me, otherwise None for session cookie)
        if remember_me:
            refresh_lifetime = settings.SIMPLE_JWT["EXTENDED_REFRESH_TOKEN_LIFETIME"]
            max_age = int(refresh_lifetime.total_seconds())
        else:
            max_age = None  # Session cookie - expires when browser closes

        response.set_cookie(
            "refresh_token",
            refresh_token,
            max_age=max_age,
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )


class AdminCookieTokenObtainPairView(CookieTokenObtainPairView):
    """
    Admin-only login. Issues the same httpOnly JWT cookies as
    CookieTokenObtainPairView, but requires is_staff=True and does not
    require (or care about) a Candidate/Recruiter profile.

    For staff accounts used to operate admin-only API endpoints (e.g. the
    manual email campaign send) that aren't tied to a candidate or
    recruiter — CookieTokenObtainPairView rejects those because it
    requires user_type to be 'candidate' or 'recruiter'.
    """

    @extend_schema(
        summary="Log in as admin (cookie-based JWT)",
        description="Authenticate with email + password for a staff (is_staff=True) account. "
                    "On success, sets httpOnly cookies (access_token, refresh_token), same as "
                    "the candidate/recruiter login. No Candidate/Recruiter profile required.",
        request=inline_serializer(
            "AdminLoginRequest",
            fields={
                "email": serializers.EmailField(help_text="User email address"),
                "password": serializers.CharField(write_only=True, help_text="User password"),
                "remember_me": serializers.BooleanField(
                    required=False, default=False,
                    help_text="Extend refresh token lifetime (30 days vs session cookie)",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "AdminLoginSuccessResponse",
                    fields={
                        "user": inline_serializer(
                            "AdminLoginUserInfo",
                            fields={"email": serializers.EmailField()},
                        ),
                    },
                ),
                description="Login successful. httpOnly cookies (access_token, refresh_token) are set.",
            ),
            400: OpenApiResponse(description="Invalid credentials or account is not staff"),
        },
    )
    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        remember_me = request.data.get("remember_me", False)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError:
            # Same generic message regardless of failure reason, to avoid
            # leaking whether an email exists or is staff (user enumeration).
            return APIResponse.error(
                message=_("Invalid credentials"),
                code="INVALID_CREDENTIALS",
                status_code=400,
            )

        user = serializer.user

        if not user.is_staff:
            return APIResponse.error(
                message=_("Invalid credentials"),
                code="INVALID_CREDENTIALS",
                status_code=400,
            )

        activate_request_timezone(request, user)

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        access_token = serializer.validated_data["access"]
        refresh_token_str = serializer.validated_data["refresh"]

        if remember_me:
            refresh_obj = RefreshToken(refresh_token_str)
            refresh_obj.set_exp(
                from_time=timezone.now(),
                lifetime=settings.SIMPLE_JWT["EXTENDED_REFRESH_TOKEN_LIFETIME"],
            )
            refresh_token_str = str(refresh_obj)

        new_response = APIResponse.success(
            data={"user": {"email": email}},
            message=_("Login successful"),
        )
        self._set_auth_cookies(new_response, access_token, refresh_token_str, remember_me)

        return new_response


@extend_schema(
    request=None,
    responses={
        200: inline_serializer(
            name="TokenRefreshSuccess",
            fields={
                "message": serializers.CharField(default="Token refreshed successfully")
            },
        ),
        401: inline_serializer(
            name="TokenRefreshError",
            fields={
                "error": serializers.CharField(
                    default="Refresh token not found or invalid"
                )
            },
        ),
    },
)
class CookieTokenRefreshView(APIView):
    """
    Custom refresh view that gets refresh token from cookie.
    Preserves the original token's expiration time (remember_me support).
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return APIResponse.unauthorized(
                message=_("Refresh token not found in cookies"),
            )

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            # If token rotation is enabled, get new refresh token
            new_refresh_token = (
                str(refresh)
                if settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS")
                else refresh_token
            )

            response = APIResponse.success(
                message=_("Token refreshed successfully"),
            )

            # Set new tokens in cookies (preserves original expiration)
            self._set_auth_cookies(response, access_token, new_refresh_token)

            return response

        except TokenError:
            return APIResponse.unauthorized(
                message=_("Invalid refresh token"),
            )

    def _set_auth_cookies(self, response, access_token, refresh_token):
        """
        Set httpOnly cookies for access and refresh tokens.
        Automatically calculates cookie expiration from token's actual exp claim.
        This preserves remember_me functionality during token rotation.
        """
        # Access token cookie (always 15 minutes)
        access_token_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        response.set_cookie(
            "access_token",
            access_token,
            max_age=int(access_token_lifetime.total_seconds()),
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )

        # Refresh token cookie - calculate remaining lifetime from token itself
        try:
            refresh_obj = RefreshToken(refresh_token)
            # Get expiration timestamp from token
            exp_timestamp = refresh_obj.payload.get('exp')

            if exp_timestamp:
                # Calculate remaining time until expiration
                from datetime import datetime
                now = datetime.utcnow().timestamp()
                remaining_seconds = int(exp_timestamp - now)

                # Use remaining time (handles both 7-day and 30-day tokens)
                # But only set max_age if token was created with remember_me
                # We check if remaining time is significantly longer than default refresh lifetime
                default_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()

                # If token expires much later than default, it was a remember_me token
                if remaining_seconds > default_lifetime * 1.5:  # 1.5x buffer for clock skew
                    max_age = max(remaining_seconds, 0)
                else:
                    # Short-lived token, use session cookie
                    max_age = None
            else:
                # Fallback to session cookie if exp claim is missing
                max_age = None
        except Exception:
            # Fallback to session cookie on any error
            max_age = None

        response.set_cookie(
            "refresh_token",
            refresh_token,
            max_age=max_age,
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )


@extend_schema(
    request=None,
    responses={
        200: inline_serializer(
            name="TokenVerifySuccess",
            fields={"message": serializers.CharField(default="Token is valid")},
        ),
        401: inline_serializer(
            name="TokenVerifyError",
            fields={
                "error": serializers.CharField(
                    default="Access token not found or invalid"
                )
            },
        ),
    },
)
class CookieTokenVerifyView(APIView):
    """Verify access token from cookie"""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        access_token = request.COOKIES.get("access_token")

        if not access_token:
            return APIResponse.unauthorized(
                message=_("Access token not found in cookies"),
            )

        try:
            from rest_framework_simplejwt.tokens import UntypedToken

            UntypedToken(access_token)
            return APIResponse.success(message=_("Token is valid"))
        except TokenError:
            return APIResponse.unauthorized(
                message=_("Invalid access token"),
            )


@extend_schema(
    request=None,
    responses={200: None},
)
class CookieLogoutView(APIView):
    """Logout view that clears httpOnly cookies"""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        # Blacklist refresh token if it exists
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                logger.warning("Invalid refresh token during logout")

        # Drop any chat WebSocket this user still holds. Without this a
        # logged-out tab keeps receiving live messages until its socket
        # happens to break, which on a healthy connection is never.
        from apps.conversations.realtime import disconnect_users

        disconnect_users([request.user.id], reason="logout")

        response = APIResponse.success(
            message=_("Successfully logged out"),
        )

        # Delete cookies (must match set_cookie parameters exactly)
        response.delete_cookie(
            "access_token",
            path="/",
            samesite="None",
        )
        response.delete_cookie(
            "refresh_token",
            path="/",
            samesite="None",
        )

        return response
