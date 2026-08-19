import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.authentication.models import Candidate, CustomUser
from apps.authentication.services.consent_service import ConsentService
from apps.authentication.services.phone_otp_service import (
    OtpCooldownError,
    OtpDailyLimitError,
    OtpDeliveryError,
    OtpMaxAttemptsError,
    PhoneOtpService,
)
from core.responses import APIResponse
from utils.language import get_request_language
from utils.phone import InvalidPhoneNumber, normalize_uz_phone

logger = logging.getLogger(__name__)


@extend_schema(
    request=inline_serializer("PhoneRegistrationSendOtpRequest", fields={"phone": serializers.CharField()}),
    responses={200: None},
)
class SendPhoneRegistrationOtpView(APIView):
    """
    POST /auth/phone/register/send-otp/

    Unauthenticated: the first step of phone-based candidate signup. Reuses
    the same OTP infra as the authenticated phone-verification flow, since
    both are keyed by phone number, not by an existing account.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw_phone = request.data.get("phone")
        if not raw_phone:
            return APIResponse.bad_request(message=_("Phone number is required."))

        try:
            phone = normalize_uz_phone(raw_phone)
        except InvalidPhoneNumber as e:
            return APIResponse.bad_request(message=str(e))

        if CustomUser.objects.filter(phone=phone, phone_verified_at__isnull=False).exists():
            return APIResponse.conflict(message=_("An account already exists for this phone number."))

        try:
            PhoneOtpService.send(phone, language=get_request_language())
        except OtpCooldownError:
            return APIResponse.error(message=_("Please wait before requesting another code."), code="OTP_COOLDOWN", status_code=429)
        except OtpDailyLimitError:
            return APIResponse.error(message=_("Daily verification code limit reached for this number."), code="OTP_DAILY_LIMIT", status_code=429)
        except OtpDeliveryError:
            return APIResponse.server_error(message=_("Failed to send verification code. Please try again later."))

        return APIResponse.success(message=_("Verification code sent."))


@extend_schema(
    request=inline_serializer(
        "PhoneRegistrationVerifyRequest",
        fields={
            "phone": serializers.CharField(),
            "code": serializers.CharField(),
            "email": serializers.EmailField(),
            "password": serializers.CharField(write_only=True),
        },
    ),
    responses={201: None},
)
class VerifyPhoneRegistrationView(APIView):
    """
    POST /auth/phone/register/verify/

    Confirms the code and creates a new, already-phone-verified candidate
    account in one step (no separate set-password email — phone OTP already
    proved liveness). Shared by web and mobile; the caller (web cookie login
    vs mobile /auth/mobile/login/) still authenticates normally afterwards.

    Scoping note: still requires an email — CustomUser.email is a required,
    unique field used throughout the platform (notifications, USERNAME_FIELD,
    etc). Making it optional for pure phone-only accounts is a materially
    larger, separate change; this endpoint adds phone as a *second* verified
    identifier at signup, it doesn't remove email.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        raw_phone = request.data.get("phone")
        code = request.data.get("code")
        email = request.data.get("email")
        password = request.data.get("password")

        if not all([raw_phone, code, email, password]):
            return APIResponse.bad_request(message=_("phone, code, email and password are all required."))

        try:
            phone = normalize_uz_phone(raw_phone)
        except InvalidPhoneNumber as e:
            return APIResponse.bad_request(message=str(e))

        if CustomUser.objects.filter(email__iexact=email).exists():
            return APIResponse.conflict(message=_("An account with this email already exists."))
        if CustomUser.objects.filter(phone=phone, phone_verified_at__isnull=False).exists():
            return APIResponse.conflict(message=_("An account already exists for this phone number."))

        try:
            validate_password(password)
        except DjangoValidationError as e:
            return APIResponse.validation_error(field_errors={"password": e.messages})

        try:
            is_valid = PhoneOtpService.verify(phone, code)
        except OtpMaxAttemptsError:
            return APIResponse.error(message=_("Too many incorrect attempts. Request a new code."), code="OTP_MAX_ATTEMPTS", status_code=429)

        if not is_valid:
            return APIResponse.error(message=_("Invalid or expired verification code."), code="OTP_INVALID", status_code=400)

        try:
            user = Candidate(email=email, phone=phone, phone_verified_at=timezone.now(), is_active=True, is_candidate=True)
            user.set_password(password)
            user.save()
        except IntegrityError:
            logger.warning("Race creating phone-registered candidate for phone=%s email=%s", phone, email)
            return APIResponse.conflict(message=_("An account with this phone number or email already exists."))

        try:
            ConsentService.create_consents_for_entity(
                consenter=user,
                entity_type="candidate",
                ip_address=ConsentService.get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                request=request,
            )
        except ValueError as exc:
            logger.warning("Could not create consent records for phone-registered candidate %s: %s", email, exc)

        return APIResponse.success(
            data={"email": user.email, "phone": phone},
            message=_("Account created. You can now log in with your phone or email."),
            status_code=201,
        )
