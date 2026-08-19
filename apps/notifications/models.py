from django.db import models
from django.utils import timezone

from utils.abstract_model import AbstractBaseModel

from fcm_django.models import FCMDevice


class Notification(AbstractBaseModel):
    """
    Represents a notification created in the system.
    """

    class NotificationType(models.TextChoices):
        """
        Different types of notifications.
        """

        APPLICATION_APPLIED = "application_applied", "Application Applied"
        APPLICATION_STATUS_UPDATED = (
            "application_status_updated",
            "Application Status Updated",
        )
        APPLICATION_ACCEPTED = "application_accepted", "Application Accepted"
        APPLICATION_REJECTED = "application_rejected", "Application Rejected"
        APPLICATION_OFFERED = (
            "application_offered",
            "Application Offered",
        )
        NEW_JOB_MATCH = "new_job_match", "New Job Match"
        PLATFORM_ANNOUNCEMENT = "platform_announcement", "Platform Announcement"
        PROFILE_UPDATE_REMINDER = "profile_update_reminder", "Profile Update Reminder"
        INTERVIEW_SCHEDULED = "interview_scheduled", "Interview Scheduled"
        INTERVIEW_REMINDER = "interview_reminder", "Interview Reminder"

    title = models.CharField(max_length=255, db_index=True)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
        default=NotificationType.PLATFORM_ANNOUNCEMENT,
        db_index=True,
    )
    data = models.JSONField(blank=True, null=True)

    # Indicates whether the notification was sent to all users
    sent_to_all = models.BooleanField(default=False, db_index=True)

    # Statistics
    sent_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notifications",
    )

    def __str__(self):
        return f"{self.title} - {self.notification_type}"

    @property
    def success_rate(self):
        """
        Calculates the success rate of the notification.
        """
        if self.sent_count > 0:
            return round((self.success_count / self.sent_count) * 100, 2)
        return 0

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        indexes = [
            models.Index(fields=["-created_at", "notification_type"]),
            models.Index(fields=["sent_to_all", "-created_at"]),
        ]


class NotificationRecipient(AbstractBaseModel):
    """
    Represents a user who should receive a notification.
    """

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="recipients"
    )
    user = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(blank=True, null=True)

    def mark_as_read(self):
        """
        Mark notification as read
        """
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def __str__(self):
        return f"{self.user.email} -> {self.notification.title}"

    class Meta:
        verbose_name = "Notification Recipient"
        verbose_name_plural = "Notification Recipients"
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "user"], name="unique_notification_user"
            )
        ]
        indexes = [
            # models.Index(fields=['user', '-notification__created_at']),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["notification", "user"]),
        ]


class NotificationLog(AbstractBaseModel):
    """
    Tracks delivery attempts of a notification to a specific device.
    """

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        DELIVERED = "delivered", "Delivered"

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="logs"
    )
    user = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="notification_logs",
    )
    device = models.ForeignKey(
        FCMDevice, on_delete=models.CASCADE, related_name="fcm_logs"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.SENT
    )
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Log for {self.notification.title} to {self.user.email} - {self.status}"

    class Meta:
        verbose_name = "Notification Log"
        verbose_name_plural = "Notification Logs"
        ordering = ["-created_at"]
