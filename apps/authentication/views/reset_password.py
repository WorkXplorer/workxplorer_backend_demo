from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from utils import encode_uid, decode_uid
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from apps.profiles.models import RecruiterProfile
from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Recruiter
from apps.authentication.serializers.user import (
    ResetPasswordRequestSerializer,
    ResetPasswordConfirmSerializer,
    SetPasswordSerializer,
)
from apps.authentication.services.consent_service import ConsentService
from apps.general.services.email_service import send_password_reset_email
from apps.general.services.language_cache import LanguageCacheService
from core.responses import APIResponse
from utils.language import get_request_language
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
    inline_serializer,
)
from django.utils.translation import gettext as _

# Get the custom user model
User = get_user_model()

# Token generator instance for password reset
token_generator = PasswordResetTokenGenerator()


class RequestPasswordResetAPIView(APIView):
    """
    API endpoint to request a password reset.
    Accepts a user's email and sends a password reset link if the user exists.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        description="Request password reset. Sends email with reset link.",
        request=ResetPasswordRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=dict,
                description="Password reset email sent.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "detail": "Password reset link has been sent to your email."
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=dict,
                description="User not found.",
                examples=[
                    OpenApiExample(
                        "User Not Found",
                        value={"detail": "This user does not exist."},
                        status_codes=["400"],
                    )
                ],
            ),
        },
    )
    def post(self, request):
        """
        Handle POST request to send a password reset link via email.

        Example request:
        {
            "email": "user@example.com"
        }
        """
        serializer = ResetPasswordRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data.get("email")
            if not email:
                return APIResponse.validation_error(
                    message=_("Email is required."),
                    field_errors={"email": ["This field is required."]},
                )

            # Get requested language from headers
            language = get_request_language()

            try:
                # Try to get the user by email
                user = User.objects.get(email=email)

                # Generate token and UID
                token = token_generator.make_token(user)
                uid = encode_uid(user.pk)

                # Build reset URL (frontend link)
                reset_url = f"{settings.FRONTEND_URL}/recover/{uid}/{token}/"

                # Prepare context for email template
                context = {
                    "user": user,
                    "reset_url": reset_url,
                    "site_name": getattr(settings, "SITE_NAME", "Our Site"),
                }

                # Send reset email
                send_password_reset_email(user.email, context, language=language)

                return APIResponse.success(
                    message=_("Password reset link has been sent to your email."),
                )
            except User.DoesNotExist:
                return APIResponse.bad_request(
                    message=_("This user does not exist."),
                )

        return APIResponse.validation_error(
            message=_("Validation failed"),
            field_errors=serializer.errors,
        )


class ResetPasswordConfirmAPIView(APIView):
    """
    API endpoint to confirm password reset.
    Accepts UID, token, and the new password, then updates the user's password.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        description="Confirm password reset with token.",
        request=ResetPasswordConfirmSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="ResetPasswordConfirmSuccessResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "message": serializers.CharField(),
                        "data": inline_serializer(
                            name="ResetPasswordConfirmData",
                            fields={"is_company_admin": serializers.BooleanField(required=False)},
                        ),
                        "timestamp": serializers.DateTimeField(),
                    },
                ),
                description=(
                    "Password reset succeeded. Response also sets auth cookies: "
                    "access_token and refresh_token."
                ),
                examples=[
                    OpenApiExample(
                        "Candidate Success",
                        value={
                            "success": True,
                            "message": "Password has been reset successfully.",
                            "data": {},
                            "timestamp": "2026-03-30T10:15:00Z",
                        },
                        status_codes=["200"],
                    ),
                    OpenApiExample(
                        "Recruiter Success",
                        value={
                            "success": True,
                            "message": "Password has been reset successfully.",
                            "data": {"is_company_admin": False},
                            "timestamp": "2026-03-30T10:15:00Z",
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=inline_serializer(
                    name="ResetPasswordConfirmErrorResponse",
                    fields={
                        "success": serializers.BooleanField(default=False),
                        "error": inline_serializer(
                            name="ResetPasswordConfirmError",
                            fields={
                                "code": serializers.CharField(),
                                "message": serializers.CharField(),
                                "details": serializers.JSONField(required=False),
                                "field_errors": serializers.DictField(
                                    child=serializers.ListField(
                                        child=serializers.CharField(),
                                        required=False,
                                    ),
                                    required=False,
                                ),
                            },
                        ),
                        "timestamp": serializers.DateTimeField(),
                    },
                ),
                description="Invalid/expired link or validation error.",
                examples=[
                    OpenApiExample(
                        "Invalid Or Expired Link",
                        value={
                            "success": False,
                            "error": {
                                "code": "BAD_REQUEST",
                                "message": "Invalid or expired reset link.",
                            },
                            "timestamp": "2026-03-30T10:15:00Z",
                        },
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Validation Error",
                        value={
                            "success": False,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Validation failed",
                                "field_errors": {
                                    "password": ["This field is required."]
                                },
                            },
                            "timestamp": "2026-03-30T10:15:00Z",
                        },
                        status_codes=["400"],
                    )
                ],
            ),
        },
    )
    def post(self, request):
        """
        Handle POST request to reset password using a valid token.

        Example request:
        {
            "uid": "encoded_user_id",
            "token": "reset_token",
            "password": "new_password",
            "confirm_password": "new_password"
        }
        """
        serializer = ResetPasswordConfirmSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # Safely get uid from validated data
                uid_b64 = (
                    serializer.validated_data.get("uid")
                    if isinstance(serializer.validated_data, dict)
                    else None
                )

                if not uid_b64:
                    return APIResponse.bad_request(
                        message=_("Invalid reset link."),
                    )

                # Decode UID and get user (guard against decode errors)
                try:
                    uid = decode_uid(uid_b64)
                except (TypeError, ValueError, OverflowError):
                    return APIResponse.bad_request(
                        message=_("Invalid reset link."),
                    )

                user = User.objects.get(pk=uid)

                # Validate the token safely
                token = (
                    serializer.validated_data.get("token")
                    if isinstance(serializer.validated_data, dict)
                    else None
                )
                if not token or not token_generator.check_token(user, token):
                    return APIResponse.bad_request(
                        message=_("Invalid or expired reset link."),
                    )

                response_data = {}
                if getattr(user, "is_recruiter", False):
                    is_company_admin = False
                    profile = RecruiterProfile.objects.filter(recruiter=user).first()
                    if profile and getattr(profile, "is_admin", False):
                        is_company_admin = True
                    response_data = {"is_company_admin": is_company_admin}

                # Set the new password
                password = (
                    serializer.validated_data.get("password")
                    if isinstance(serializer.validated_data, dict)
                    else None
                )
                if not password:
                    return APIResponse.validation_error(
                        message=_("Password is required."),
                        field_errors={"password": [_("This field is required.")]},
                    )
                user.set_password(password)
                if not user.preferred_language:
                    user.preferred_language = get_request_language()
                user.save()
                LanguageCacheService.set_user_language(str(user.id), user.preferred_language)

                # Generate tokens
                refresh = RefreshToken.for_user(user)
                access = refresh.access_token

                response = APIResponse.success(
                    data=response_data,
                    message=_("Password has been reset successfully."),
                )

                # Use the same cookie setting method as CookieTokenObtainPairView
                self._set_auth_cookies(response, str(access), str(refresh))

                return response

            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                return APIResponse.bad_request(
                    message=_("Invalid reset link."),
                )

        return APIResponse.validation_error(
            message=_("Validation failed"),
            field_errors=serializer.errors,
        )

    def _set_auth_cookies(self, response, access_token, refresh_token):
        """
        Set httpOnly cookies for access and refresh tokens
        (Same method as CookieTokenObtainPairView)
        """
        # Access token cookie
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

        # Refresh token cookie
        refresh_token_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        response.set_cookie(
            "refresh_token",
            refresh_token,
            max_age=int(refresh_token_lifetime.total_seconds()),
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )


class SetPasswordView(APIView):
    """
    Unified API endpoint for both candidates and recruiters to set their
    password after registration/approval.

    Automatically detects the user type from the UID:
    - Candidate: activates account, sets password.
    - Recruiter: activates account, sets password, records consent
      (agreed_to_all_consents is required for recruiters).

    Returns user_type in the response ("candidate" or "recruiter").
    """

    permission_classes = [AllowAny]

    @extend_schema(
        description=(
            "Set password for a newly registered user (candidate or recruiter). "
            "The user type is auto-detected from the UID. "
            "For recruiters, agreed_to_all_consents is required."
        ),
        request=SetPasswordSerializer,
        responses={
            200: OpenApiResponse(
                response=dict,
                description="Password set successfully.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "message": "Password has been set successfully.",
                            "data": {"user_type": "candidate"},
                            "timestamp": "2026-03-04T12:00:00Z",
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=dict,
                description="Invalid token, validation error, or missing consent.",
                examples=[
                    OpenApiExample(
                        "Invalid Token",
                        value={
                            "success": False,
                            "message": "Invalid or expired set-password link.",
                            "error": {"code": "BAD_REQUEST"},
                            "timestamp": "2026-03-04T12:00:00Z",
                        },
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Missing Consent",
                        value={
                            "success": False,
                            "message": "Validation failed",
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "field_errors": {
                                    "agreed_to_all_consents": [
                                        "You must agree to all required policies to activate your account"
                                    ]
                                },
                            },
                            "timestamp": "2026-03-04T12:00:00Z",
                        },
                        status_codes=["400"],
                    ),
                ],
            ),
        },
    )
    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(
                message=_("Validation failed"),
                field_errors=serializer.errors,
            )

        try:
            uid_b64 = serializer.validated_data.get("uid")
            if not uid_b64:
                return APIResponse.bad_request(
                    message=_("Invalid set-password link."),
                )

            # Decode UID
            try:
                uid = decode_uid(uid_b64)
            except (TypeError, ValueError, OverflowError):
                return APIResponse.bad_request(
                    message=_("Invalid set-password link."),
                )

            # Detect user type: try Candidate first, then Recruiter
            user, user_type = self._resolve_user(uid)
            if user is None:
                return APIResponse.bad_request(
                    message=_("Invalid set-password link."),
                )

            # Validate the token
            token = serializer.validated_data.get("token")
            if not token or not token_generator.check_token(user, token):
                return APIResponse.bad_request(
                    message=_("Invalid or expired set-password link."),
                )

            # For recruiters, consent is required
            if user_type == "recruiter":
                agreed = serializer.validated_data.get("agreed_to_all_consents")
                if not agreed:
                    return APIResponse.validation_error(
                        message=_("Validation failed"),
                        field_errors={
                            "agreed_to_all_consents": [
                                _("You must agree to all required policies to activate your account")
                            ]
                        },
                    )

            # Set the new password and activate account
            password = serializer.validated_data.get("password")
            user.set_password(password)
            user.is_active = True
            if user_type == "recruiter":
                user.is_waiting_approval = False
            if not user.preferred_language:
                user.preferred_language = get_request_language()
            user.save()
            LanguageCacheService.set_user_language(str(user.id), user.preferred_language)

            # Attach any pending anonymous quiz result (case 2 of the quiz flow)
            if user_type == "candidate":
                try:
                    from apps.authentication.models import Candidate as _Candidate
                    from apps.quiz.services.pending_quiz_service import attach_pending_to_candidate
                    _candidate = _Candidate.objects.filter(pk=user.pk).first()
                    if _candidate:
                        attach_pending_to_candidate(_candidate)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception(
                        "Failed to attach pending quiz result after set-password for user %s", user.pk
                    )

            # Record consent for recruiters
            if user_type == "recruiter" and serializer.validated_data.get("agreed_to_all_consents"):
                ip_address = ConsentService.get_client_ip(request)
                user_agent = request.headers.get('User-Agent', '') if request else ''
                ConsentService.create_consents_for_entity(
                    consenter=user,
                    entity_type="recruiter",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )

            # Generate JWT tokens for automatic login
            refresh = RefreshToken.for_user(user)
            access = refresh.access_token

            response = APIResponse.success(
                data={"user_type": user_type},
                message=_("Password has been set successfully."),
            )
            self._set_auth_cookies(response, str(access), str(refresh))
            return response

        except (TypeError, ValueError, OverflowError):
            return APIResponse.bad_request(
                message=_("Invalid set-password link."),
            )

    @staticmethod
    def _resolve_user(uid):
        """
        Resolve user from UID. Returns (user_instance, user_type_str) or (None, None).
        Tries Candidate first, then Recruiter — exactly two queries at most.
        """
        try:
            return Candidate.objects.get(pk=uid), "candidate"
        except Candidate.DoesNotExist:
            pass
        try:
            return Recruiter.objects.get(pk=uid), "recruiter"
        except Recruiter.DoesNotExist:
            return None, None

    def _set_auth_cookies(self, response, access_token, refresh_token):
        """Set httpOnly cookies for access and refresh tokens."""
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

        refresh_token_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
        response.set_cookie(
            "refresh_token",
            refresh_token,
            max_age=int(refresh_token_lifetime.total_seconds()),
            httponly=True,
            samesite="None",
            secure=True,
            path="/",
        )


# View functions for URL configuration
request_password_reset_view = RequestPasswordResetAPIView.as_view()
reset_password_confirm_view = ResetPasswordConfirmAPIView.as_view()
set_password_view = SetPasswordView.as_view()
