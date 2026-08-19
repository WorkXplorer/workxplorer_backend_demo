import logging
from typing import Dict, List, Any, Optional

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import QuerySet

from firebase_admin import messaging, exceptions as firebase_exceptions
from fcm_django.models import FCMDevice

from apps.notifications.models import Notification, NotificationLog
from apps.notifications.constants import (
    CACHE_KEY_UNREAD_COUNT,
    CACHE_KEY_NOTIFICATIONS_PATTERN,
    CACHE_KEY_NOTIFICATIONS_VERSION,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service class for handling notification operations.
    Provides reusable methods for sending push notifications via FCM.
    """

    INVALID_TOKEN_ERROR_MARKERS = (
        "registration token is not a valid fcm registration token",
        "device unregistered",
        "notregistered",
        "requested entity was not found",
    )

    @staticmethod
    def _is_invalid_token_error(error: Exception) -> bool:
        """Return True when Firebase reports that a device token is no longer usable."""
        if isinstance(error, messaging.UnregisteredError):
            return True

        if isinstance(error, firebase_exceptions.InvalidArgumentError):
            return "registration token" in str(error).lower()

        error_message = str(error).lower()
        return any(
            marker in error_message
            for marker in NotificationService.INVALID_TOKEN_ERROR_MARKERS
        )

    @staticmethod
    def _deactivate_device(device: FCMDevice, reason: Exception) -> None:
        """Disable a device token after Firebase confirms it is invalid or stale."""
        if not device.active:
            return

        device.active = False
        device.save(update_fields=["active"])
        logger.warning(
            "Deactivated invalid FCM device %s for user %s: %s",
            device.id,
            device.user_id,
            reason,
        )

    @staticmethod
    def _get_platform_config(
            device_type: str,
            data: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Get platform-specific FCM configuration for the device type."""
        config: Dict[str, Any] = {}

        if device_type == "android":
            config["android"] = messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="default_channel",
                    sound="default",
                    priority="high",
                    default_sound=True,
                    default_vibrate_timings=True,
                ),
            )
        elif device_type == "ios":
            config["apns"] = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound="default",
                        badge=1,
                        content_available=True,
                        mutable_content=True,
                        category="NOTIFICATION",
                    ),
                ),
            )
        elif device_type == "web":
            link_url = (data or {}).get("url", "")
            webpush_kwargs: Dict[str, Any] = {
                "notification": messaging.WebpushNotification(
                    icon="/icon.png",
                    badge="/badge.png",
                ),
            }
            if link_url.startswith("https://"):
                webpush_kwargs["fcm_options"] = messaging.WebpushFCMOptions(
                    link=link_url,
                )
            config["webpush"] = messaging.WebpushConfig(**webpush_kwargs)

        return config

    @staticmethod
    def send_to_device(
            device: FCMDevice,
            title: str,
            message: str,
            data: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Send a push notification to a single device.

        Args:
            device: FCMDevice instance
            title: Notification title
            message: Notification message/body
            data: Optional dictionary of additional data

        Returns:
            bool: True if successful, False otherwise
        """
        string_data = {k: str(v) for k, v in (data or {}).items()}

        try:
            # Build platform-specific FCM config for the device type.
            # Without this, Android 8+ devices with custom channels
            # and iOS devices may silently drop notifications.
            platform_config = NotificationService._get_platform_config(
                device.type, string_data
            )

            fcm_message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=message,
                ),
                data=string_data,
                token=device.registration_id,
                **platform_config,
            )

            response = messaging.send(fcm_message)
            logger.info(
                "Successfully sent notification to device %s (%s): %s",
                device.id, device.type, response,
            )

            # Log the delivery attempt for debugging per-device issues.
            notif_id = string_data.get("notification_id")
            if notif_id:
                try:
                    NotificationLog.objects.create(
                        notification_id=notif_id,
                        user_id=device.user_id,
                        device=device,
                        status=NotificationLog.Status.SENT,
                    )
                except Exception as log_exc:
                    logger.error(
                        "Failed to persist SENT NotificationLog for notification %s on device %s: %s",
                        notif_id, device.id, log_exc,
                    )

            return True

        except Exception as e:
            if NotificationService._is_invalid_token_error(e):
                NotificationService._deactivate_device(device, e)

            logger.error(
                "Failed to send notification to device %s (%s): %s",
                device.id, device.type, e,
            )

            notif_id = string_data.get("notification_id")
            if notif_id:
                try:
                    NotificationLog.objects.create(
                        notification_id=notif_id,
                        user_id=device.user_id,
                        device=device,
                        status=NotificationLog.Status.FAILED,
                        error_message=str(e)[:500],
                    )
                except Exception as log_exc:
                    logger.error(
                        "Failed to persist FAILED NotificationLog for notification %s on device %s: %s",
                        notif_id, device.id, log_exc,
                    )

            return False

    @staticmethod
    def send_to_devices(
            devices: List[FCMDevice],
            title: str,
            message: str,
            data: Optional[Dict[str, str]] = None,
    ) -> Dict[str, int]:
        """
        Send a push notification to multiple devices.

        Args:
            devices: List of FCMDevice instances
            title: Notification title
            message: Notification message/body
            data: Optional dictionary of additional data

        Returns:
            Dict with 'success_count' and 'failure_count'
        """
        devices = list(devices)

        if not devices:
            return {
                "success_count": 0,
                "failure_count": 0,
                "total_count": 0,
            }

        string_data = {k: str(v) for k, v in (data or {}).items()}
        success_count = 0
        failure_count = 0

        if len(devices) > 1:
            try:
                multicast_message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title=title,
                        body=message,
                    ),
                    data=string_data,
                    tokens=[device.registration_id for device in devices],
                )

                response = messaging.send_each_for_multicast(multicast_message)

                for device, send_response in zip(devices, response.responses):
                    if send_response.success:
                        success_count += 1
                        continue

                    failure_count += 1
                    if NotificationService._is_invalid_token_error(
                            send_response.exception
                    ):
                        NotificationService._deactivate_device(
                            device, send_response.exception
                        )
                    logger.error(
                        "Failed to send notification to device %s: %s",
                        device.id,
                        send_response.exception,
                    )

                return {
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "total_count": success_count + failure_count,
                }

            except Exception as e:
                logger.warning(
                    "send_each_for_multicast failed, falling back to individual sends: %s",
                    e,
                )

        for device in devices:
            if NotificationService.send_to_device(device, title, message, string_data):
                success_count += 1
            else:
                failure_count += 1

        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "total_count": success_count + failure_count,
        }

    @staticmethod
    def send_to_user(
            user: User,  # type: ignore
            notification: Notification,
            title: str,
            message: str,
            data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send push notification to all devices of a single user.

        Returns:
            Dict with success status and counts
        """
        try:
            # Single query — evaluate immediately so we avoid a redundant EXISTS check.
            devices = list(FCMDevice.objects.filter(user=user, active=True))

            if not devices:
                return {
                    "success": False,
                    "devices_count": 0,
                    "success_count": 0,
                }

            message_data = {
                "notification_id": str(notification.id),
                "notification_type": notification.notification_type,
                "timestamp": str(notification.created_at),
            }
            if data:
                message_data.update(data)

            message_data_str = {k: str(v) for k, v in message_data.items()}

            result = NotificationService.send_to_devices(devices, title, message, message_data_str)

            return {
                "success": result["success_count"] > 0,
                "devices_count": result["total_count"],
                "success_count": result["success_count"],
            }

        except Exception as e:
            logger.error("Error sending push notification to user %s: %s", user.id, e)
            return {
                "success": False,
                "devices_count": 0,
                "success_count": 0,
            }

    @staticmethod
    def get_active_devices(user: Optional[User] = None) -> QuerySet[FCMDevice]:  # type: ignore
        """
        Get active FCM devices for a user or all devices.

        Args:
            user: Optional User instance. If None, returns all active devices.

        Returns:
            QuerySet of FCMDevice
        """
        if user:
            return FCMDevice.objects.filter(user=user, active=True)
        return FCMDevice.objects.filter(active=True)

    @staticmethod
    def clear_user_notification_cache(user_id: str) -> None:
        """
        Clear notification-related cache for a user.

        Args:
            user_id: User ID (UUID as string)
        """
        try:
            cache.delete(CACHE_KEY_UNREAD_COUNT.format(user_id=user_id))
            current_version = NotificationService.get_user_notification_cache_version(
                user_id
            )
            cache.set(
                CACHE_KEY_NOTIFICATIONS_VERSION.format(user_id=user_id),
                current_version + 1,
                None,
            )
            # Try to delete pattern-based cache keys if supported
            try:
                cache_pattern = CACHE_KEY_NOTIFICATIONS_PATTERN.format(user_id=user_id)
                cache.delete_pattern(cache_pattern)
            except AttributeError:
                # delete_pattern might not be available on all cache backends
                logger.warning(
                    f"Cache backend doesn't support delete_pattern for user {user_id}"
                )
        except Exception as e:
            logger.warning(f"Failed to clear cache for user {user_id}: {e}")

    @staticmethod
    def get_user_notification_cache_version(user_id: str) -> int:
        """Return the current notification cache version for a user."""
        version = cache.get(CACHE_KEY_NOTIFICATIONS_VERSION.format(user_id=user_id))
        return int(version) if version is not None else 1

    @staticmethod
    def update_notification_stats(
            notification: Notification, success_count: int, failure_count: int
    ) -> None:
        """Update sent/success/failure counters without touching unrelated fields."""
        notification.sent_count = success_count + failure_count
        notification.success_count = success_count
        notification.failure_count = failure_count
        notification.save(update_fields=["sent_count", "success_count", "failure_count", "updated_at"])
