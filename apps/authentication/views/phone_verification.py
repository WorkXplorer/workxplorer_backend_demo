import logging

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.authentication.models.user import CustomUser
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
    request=inline_serializer("SendPhoneOtpRequest", fields={"phone": serializers.CharField()}),
    responses={200: None},
)
class SendPhoneOtpView(APIView):
    """
    POST /auth/phone/send-otp/

    Sends a one-time code to the authenticated user's phone number so it can
    be confirmed via /auth/phone/verify-otp/. Once verified, the phone can be
    used as an alternate login identifier alongside email.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        raw_phone = request.data.get("phone")
        if not raw_phone:
            return APIResponse.bad_request(message=_("Phone number is required."))

        try:
            phone = normalize_uz_phone(raw_phone)
        except InvalidPhoneNumber as e:
            return APIResponse.bad_request(message=str(e))

        already_verified = (
            CustomUser.objects.filter(phone=phone, phone_verified_at__isnull=False)
            .exclude(pk=request.user.pk)
            .exists()
        )
        if already_verified:
            return APIResponse.conflict(
                message=_("This phone number is already verified on another account.")
            )

        try:
            PhoneOtpService.send(phone, language=get_request_language())
        except OtpCooldownError:
            return APIResponse.error(
                message=_("Please wait before requesting another code."),
                code="OTP_COOLDOWN",
                status_code=429,
            )
        except OtpDailyLimitError:
            return APIResponse.error(
                message=_("Daily verification code limit reached for this number."),
                code="OTP_DAILY_LIMIT",
                status_code=429,
            )
        except OtpDeliveryError:
            return APIResponse.server_error(
                message=_("Failed to send verification code. Please try again later.")
            )

        return APIResponse.success(message=_("Verification code sent."))


@extend_schema(
    request=inline_serializer(
        "VerifyPhoneOtpRequest",
        fields={"phone": serializers.CharField(), "code": serializers.CharField()},
    ),
    responses={200: None},
)
class VerifyPhoneOtpView(APIView):
    """
    POST /auth/phone/verify-otp/

    Confirms the code sent by /auth/phone/send-otp/ and, on success, marks
    the phone number verified and attached to the authenticated user.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        raw_phone = request.data.get("phone")
        code = request.data.get("code")
        if not raw_phone or not code:
            return APIResponse.bad_request(message=_("Phone number and code are required."))

        try:
            phone = normalize_uz_phone(raw_phone)
        except InvalidPhoneNumber as e:
            return APIResponse.bad_request(message=str(e))

        try:
            is_valid = PhoneOtpService.verify(phone, code)
        except OtpMaxAttemptsError:
            return APIResponse.error(
                message=_("Too many incorrect attempts. Request a new code."),
                code="OTP_MAX_ATTEMPTS",
                status_code=429,
            )

        if not is_valid:
            return APIResponse.error(
                message=_("Invalid or expired verification code."),
                code="OTP_INVALID",
                status_code=400,
            )

        user = request.user
        user.phone = phone
        user.phone_verified_at = timezone.now()
        try:
            user.save(update_fields=["phone", "phone_verified_at"])
        except IntegrityError:
            logger.warning("Phone %s was claimed by another account mid-verification", phone)
            return APIResponse.conflict(
                message=_("This phone number is already verified on another account.")
            )

        return APIResponse.success(
            data={"phone": phone, "phone_verified": True},
            message=_("Phone number verified."),
        )
