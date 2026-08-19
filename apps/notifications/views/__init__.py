from .admin import (
    send_notification_view,
    send_notification_view_to_multiple_users,
    send_notification_to_recruiters,
)
from .device import register_device_view
from .user import (
    get_notification_view,
    mark_as_read_view,
    bulk_mark_as_read_view,
    send_notification_to_user_view,
)

__all__ = [
    "send_notification_view",
    "register_device_view",
    "get_notification_view",
    "mark_as_read_view",
    "bulk_mark_as_read_view",
    "send_notification_to_user_view",
    "send_notification_view_to_multiple_users",
    "send_notification_to_recruiters",
]
