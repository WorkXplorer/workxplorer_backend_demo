from django.contrib import admin
from .models import Notification, NotificationRecipient, NotificationLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "notification_type",
        "sent_count",
        "success_count",
        "failure_count",
        "created_at",
        "created_by",
    )
    search_fields = ("title", "message", "notification_type")
    list_filter = ("notification_type", "created_at")
    readonly_fields = (
        "sent_count",
        "success_count",
        "failure_count",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)


@admin.register(NotificationRecipient)
class NotificationRecipientAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "is_read", "read_at", "created_at")
    search_fields = ("notification__title", "user__username", "user__email")
    list_filter = ("is_read", "created_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "status", "created_at")
    search_fields = ("notification__title", "user__username", "user__email", "status")
    list_filter = ("status", "created_at")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
