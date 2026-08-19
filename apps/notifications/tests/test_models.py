from django.test import TestCase
from django.db.utils import IntegrityError

from apps.notifications.models import (
    Notification,
    NotificationRecipient,
    NotificationLog,
)
from apps.authentication.models import CustomUser, Candidate
from fcm_django.models import FCMDevice


class NotificationModelTests(TestCase):
    """Test suite for Notification model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.user = CustomUser.objects.create_user(
            email="admin@test.com", password="testpass123"
        )

    def test_create_notification_successfully(self):
        """Test creating a notification with valid data."""
        notification = Notification.objects.create(
            title="Application Update",
            message="Your application has been reviewed",
            notification_type=Notification.NotificationType.APPLICATION_OFFERED,
            created_by=self.user,
        )

        self.assertEqual(notification.title, "Application Update")
        self.assertEqual(notification.message, "Your application has been reviewed")
        self.assertEqual(
            notification.notification_type,
            Notification.NotificationType.APPLICATION_OFFERED,
        )
        self.assertEqual(notification.created_by, self.user)
        self.assertFalse(notification.sent_to_all)
        self.assertEqual(notification.sent_count, 0)
        self.assertEqual(notification.success_count, 0)
        self.assertEqual(notification.failure_count, 0)

    def test_notification_string_representation(self):
        """Test the string representation of Notification."""
        notification = Notification.objects.create(
            title="Welcome",
            message="Welcome to WorkXplorer",
            notification_type=Notification.NotificationType.PLATFORM_ANNOUNCEMENT,
        )

        expected_str = "Welcome - platform_announcement"
        self.assertEqual(str(notification), expected_str)

    def test_notification_success_rate_calculation(self):
        """Test the success rate property calculation."""
        notification = Notification.objects.create(
            title="Test",
            message="Test message",
            sent_count=100,
            success_count=85,
            failure_count=15,
        )

        self.assertEqual(notification.success_rate, 85.0)

    def test_notification_success_rate_with_zero_sent(self):
        """Test success rate when no notifications sent."""
        notification = Notification.objects.create(title="Test", message="Test message")

        self.assertEqual(notification.success_rate, 0)

    def test_notification_with_data_field(self):
        """Test notification with JSON data field."""
        data = {
            "application_id": "123",
            "vacancy_title": "Software Engineer",
            "action_url": "/applications/123",
        }

        notification = Notification.objects.create(
            title="Application Accepted",
            message="Congratulations!",
            notification_type=Notification.NotificationType.APPLICATION_ACCEPTED,
            data=data,
        )

        self.assertEqual(notification.data, data)
        self.assertEqual(notification.data["application_id"], "123")

    def test_notification_sent_to_all_flag(self):
        """Test the sent_to_all flag."""
        notification = Notification.objects.create(
            title="Platform Update",
            message="We've updated our platform",
            sent_to_all=True,
        )

        self.assertTrue(notification.sent_to_all)

    def test_notification_ordering(self):
        """Test that notifications are ordered by created_at descending."""
        Notification.objects.create(
            title="First", message="First notification"
        )
        Notification.objects.create(
            title="Second", message="Second notification"
        )
        Notification.objects.create(
            title="Third", message="Third notification"
        )

        notifications = Notification.objects.all()

        # Most recent first
        self.assertEqual(notifications[0].title, "Third")
        self.assertEqual(notifications[1].title, "Second")
        self.assertEqual(notifications[2].title, "First")


class NotificationRecipientModelTests(TestCase):
    """Test suite for NotificationRecipient model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.user1 = Candidate.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        cls.user2 = Candidate.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        cls.notification = Notification.objects.create(
            title="Test Notification", message="Test message"
        )

    def test_create_notification_recipient_successfully(self):
        """Test creating a notification recipient."""
        recipient = NotificationRecipient.objects.create(
            notification=self.notification, user=self.user1
        )

        self.assertEqual(recipient.notification, self.notification)
        self.assertEqual(recipient.user, self.user1)
        self.assertFalse(recipient.is_read)
        self.assertIsNone(recipient.read_at)

    def test_notification_recipient_string_representation(self):
        """Test the string representation of NotificationRecipient."""
        recipient = NotificationRecipient.objects.create(
            notification=self.notification, user=self.user1
        )

        expected_str = f"{self.user1.email} -> {self.notification.title}"
        self.assertEqual(str(recipient), expected_str)

    def test_mark_notification_as_read(self):
        """Test marking a notification as read."""
        recipient = NotificationRecipient.objects.create(
            notification=self.notification, user=self.user1
        )

        self.assertFalse(recipient.is_read)
        self.assertIsNone(recipient.read_at)

        recipient.mark_as_read()

        recipient.refresh_from_db()
        self.assertTrue(recipient.is_read)
        self.assertIsNotNone(recipient.read_at)

    def test_mark_already_read_notification(self):
        """Test marking an already read notification doesn't update read_at."""
        recipient = NotificationRecipient.objects.create(
            notification=self.notification, user=self.user1
        )

        recipient.mark_as_read()
        first_read_at = recipient.read_at

        # Mark as read again
        recipient.mark_as_read()

        recipient.refresh_from_db()
        # read_at should not change
        self.assertEqual(recipient.read_at, first_read_at)

    def test_unique_notification_user_constraint(self):
        """Test that notification-user combination must be unique."""
        NotificationRecipient.objects.create(
            notification=self.notification, user=self.user1
        )

        # Attempting to create duplicate should fail
        with self.assertRaises(IntegrityError):
            NotificationRecipient.objects.create(
                notification=self.notification, user=self.user1
            )

    def test_multiple_recipients_for_same_notification(self):
        """Test multiple users can receive the same notification."""
        recipient1 = NotificationRecipient.objects.create(
            notification=self.notification, user=self.user1
        )
        recipient2 = NotificationRecipient.objects.create(
            notification=self.notification, user=self.user2
        )

        self.assertEqual(recipient1.notification, recipient2.notification)
        self.assertNotEqual(recipient1.user, recipient2.user)


class NotificationLogModelTests(TestCase):
    """Test suite for NotificationLog model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.user = Candidate.objects.create_user(
            email="user@test.com", password="testpass123"
        )
        cls.notification = Notification.objects.create(
            title="Test Notification", message="Test message"
        )
        cls.device = FCMDevice.objects.create(
            registration_id="test-token-123", type="android", user=cls.user
        )

    def test_create_notification_log_successfully(self):
        """Test creating a notification log."""
        log = NotificationLog.objects.create(
            notification=self.notification,
            user=self.user,
            device=self.device,
            status=NotificationLog.Status.SENT,
        )

        self.assertEqual(log.notification, self.notification)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.device, self.device)
        self.assertEqual(log.status, NotificationLog.Status.SENT)
        self.assertIsNone(log.error_message)

    def test_notification_log_string_representation(self):
        """Test the string representation of NotificationLog."""
        log = NotificationLog.objects.create(
            notification=self.notification,
            user=self.user,
            device=self.device,
            status=NotificationLog.Status.DELIVERED,
        )

        expected_str = (
            f"Log for {self.notification.title} to {self.user.email} - delivered"
        )
        self.assertEqual(str(log), expected_str)

    def test_notification_log_with_error(self):
        """Test notification log with error message."""
        error_msg = "Device token invalid"
        log = NotificationLog.objects.create(
            notification=self.notification,
            user=self.user,
            device=self.device,
            status=NotificationLog.Status.FAILED,
            error_message=error_msg,
        )

        self.assertEqual(log.status, NotificationLog.Status.FAILED)
        self.assertEqual(log.error_message, error_msg)

    def test_notification_log_ordering(self):
        """Test that logs are ordered by created_at descending."""
        log1 = NotificationLog.objects.create(
            notification=self.notification,
            user=self.user,
            device=self.device,
            status=NotificationLog.Status.SENT,
        )
        log2 = NotificationLog.objects.create(
            notification=self.notification,
            user=self.user,
            device=self.device,
            status=NotificationLog.Status.DELIVERED,
        )

        logs = NotificationLog.objects.all()

        # Most recent first
        self.assertEqual(logs[0].id, log2.id)
        self.assertEqual(logs[1].id, log1.id)

    def test_notification_log_status_choices(self):
        """Test all status choices."""
        for status_value, status_label in NotificationLog.Status.choices:
            log = NotificationLog.objects.create(
                notification=self.notification,
                user=self.user,
                device=self.device,
                status=status_value,
            )
            self.assertEqual(log.status, status_value)
