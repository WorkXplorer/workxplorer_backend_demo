from django.urls import path
from apps.notifications.views import (
    send_notification_view,
    register_device_view,
    get_notification_view,
    mark_as_read_view,
    bulk_mark_as_read_view,
    send_notification_to_user_view,
    send_notification_view_to_multiple_users as bulk_notify_view,
    send_notification_to_recruiters as to_recruiters,
)

urlpatterns = [
    path("", get_notification_view, name="get-notification"),
    path("send/", send_notification_view, name="send-notification"),
    path("register-device/", register_device_view, name="register-device"),
    path("mark-as-read/<int:notification_id>/", mark_as_read_view, name="mark-as-read"),
    path("bulk-mark-as-read/", bulk_mark_as_read_view, name="bulk-mark-as-read"),
    path(
        "send-to-user/",
        send_notification_to_user_view,
        name="send-notification-to-user",
    ),
    path("send-to-multiple-users/", bulk_notify_view, name="bulk-notify-view"),
    path("send-to-recruiters/", to_recruiters, name="send-notification-to-recruiters"),
]
