# This section is for device registration for push notifications.
import logging

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.utils.translation import gettext as _

from core.responses import APIResponse

from fcm_django.models import FCMDevice
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
)

logger = logging.getLogger(__name__)


@extend_schema(
    description=(
            "Register a device for push notifications. "
            "Authenticated users can register their mobile or web devices "
            "to receive push notifications via FCM."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "registration_id": {
                    "type": "string",
                    "example": "fcm_device_token_123456",
                },
                "type": {
                    "type": "string",
                    "enum": ["android", "ios", "web"],
                    "example": "android",
                },
            },
            "required": ["registration_id"],
        }
    },
    responses={
        200: OpenApiResponse(
            description="Device successfully registered or updated",
            examples=[
                OpenApiExample(
                    "Device Registered",
                    value={
                        "message": "Device registered successfully.",
                        "device_id": 101,
                    },
                ),
                OpenApiExample(
                    "Device Updated",
                    value={"message": "Device updated successfully.", "device_id": 101},
                ),
            ],
        ),
        400: OpenApiResponse(
            description="Invalid input (missing registration_id)",
            examples=[
                OpenApiExample(
                    "Bad Request Example",
                    value={"error": "registration_id is required."},
                )
            ],
        ),
        401: OpenApiResponse(
            description="Authentication credentials were not provided or invalid",
            examples=[
                OpenApiExample(
                    "Unauthorized Example",
                    value={"detail": "Authentication credentials were not provided."},
                )
            ],
        ),
    },
)
class RegisterDeviceAPIView(APIView):
    """
    API endpoint for authenticated users to register their device for push notifications.
    Example request payload:
    {
        "registration_id": "device_registration_token",
        "type": "android"  # or "ios"
    }
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        """
        Register or update a device for push notifications.

        Uses update_or_create so that if an FCM token is reused from another
        user (e.g. shared device, recycled token), ownership is corrected to
        the current authenticated user — preventing notification misdelivery.
        """
        registration_id = request.data.get("registration_id")
        device_type = request.data.get("type", "web")  # 'android', 'ios', 'web'

        # Validate input parameters
        if not registration_id:
            return APIResponse.bad_request(
                message=_("registration_id is required.")
            )

        # Use update_or_create so the user_id is ALWAYS reset to the
        # requesting user, even if this token was previously registered
        # by a different user (token recycling / shared device scenario).
        device, created = FCMDevice.objects.update_or_create(
            registration_id=registration_id,
            defaults={
                "type": device_type,
                "user": request.user,
                "active": True,
            },
        )
        logger.info(
            "Device registration: device=%s created=%s user=%s",
            device.id, created, request.user.id,
        )

        # Enforce ONE_DEVICE_PER_USER: deactivate all other devices for
        # this user so that stale tokens don't accumulate and FCM doesn't
        # deliver to abandoned devices.
        FCMDevice.objects.filter(
            user=request.user, active=True
        ).exclude(pk=device.pk).update(active=False)

        return APIResponse.success(
            data={"device_id": device.id},
            message=(
                "Device registered successfully."
                if created
                else "Device updated successfully."
            ),
        )


register_device_view = RegisterDeviceAPIView.as_view()
