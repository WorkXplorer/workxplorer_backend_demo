"""
RQ background tasks for push notification delivery.

Keeping FCM network I/O out of the synchronous request path:
- DB writes (Notification + NotificationRecipient) happen synchronously so the
  record is visible immediately to the recipient.
- Firebase network calls and the subsequent stats UPDATE are enqueued here.
"""

import logging

logger = logging.getLogger(__name__)


def send_push_notification_task(
    notification_id: int,
    user_id: str,
    title: str,
    message: str,
    data: dict,
) -> None:
    """
    RQ task: send FCM push to all devices of *user_id* and update
    the Notification stats row.

    Args:
        notification_id: PK of the Notification record.
        user_id:         UUID string of the recipient user.
        title:           Push title.
        message:         Push body.
        data:            Extra key/value payload forwarded to FCM.
    """
    from django.contrib.auth import get_user_model

    from apps.notifications.models import Notification
    from apps.notifications.services.notification_service import NotificationService

    User = get_user_model()

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error("send_push_notification_task: user %s not found", user_id)
        return

    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.error(
            "send_push_notification_task: notification %s not found", notification_id
        )
        return

    push_result = NotificationService.send_to_user(
        user=user,
        notification=notification,
        title=title,
        message=message,
        data=data,
    )
    failure_count = max(
        push_result["devices_count"] - push_result["success_count"], 0
    )
    NotificationService.update_notification_stats(
        notification, push_result["success_count"], failure_count
    )
