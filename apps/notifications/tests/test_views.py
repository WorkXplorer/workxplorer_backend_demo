import uuid
from unittest.mock import patch
from fcm_django.models import FCMDevice

from django.utils import timezone
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.notifications.models import Notification, NotificationRecipient
from apps.notifications.services import ApplicationNotificationService
from apps.authentication.models import CustomUser


class NotificationAPITests(APITestCase):
    """
    Test suite for NotificationAPIView.
    Verifies:
    - Only authenticated users can access
    - User sees only their notifications
    - Filtering (unread + type)
    - Pagination
    """

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("get-notification")

        # Create users
        self.user = CustomUser.objects.create_user(
            email="user@test.com", password="testpass123", is_candidate=True
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@test.com", password="testpass123", is_candidate=True
        )

        # Notifications
        self.notification1 = Notification.objects.create(
            title="Job Accepted",
            message="Your application has been accepted",
            notification_type=Notification.NotificationType.APPLICATION_ACCEPTED,
        )
        self.notification2 = Notification.objects.create(
            title="Reminder",
            message="Update your profile",
            notification_type=Notification.NotificationType.PROFILE_UPDATE_REMINDER,
        )

        # Link notifications to recipients
        NotificationRecipient.objects.create(
            notification=self.notification1, user=self.user, is_read=False
        )
        NotificationRecipient.objects.create(
            notification=self.notification2, user=self.user, is_read=True
        )
        NotificationRecipient.objects.create(
            notification=self.notification1, user=self.other_user, is_read=False
        )

    def test_unauthenticated_user_cannot_access(self):
        """
        Unauthenticated users should get 401
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_user_can_see_own_notifications(self):
        """
        User sees only their notifications
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]

        notifications = data["notifications"]
        self.assertEqual(len(notifications), 2)
        self.assertNotIn("sent_count", notifications[0])
        self.assertNotIn("success_count", notifications[0])
        self.assertNotIn("failure_count", notifications[0])

        titles = [n["title"] for n in notifications]
        self.assertIn("Job Accepted", titles)
        self.assertIn("Reminder", titles)

    def test_only_unread_filter(self):
        """
        Return only unread notifications if ?only_unread=true
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"only_unread": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifications = response.json()["data"]["notifications"]

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["title"], "Job Accepted")
        self.assertFalse(notifications[0]["is_read"])

    def test_filter_by_type(self):
        """
        Return notifications filtered by type
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"type": "profile_update_reminder"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notifications = response.json()["data"]["notifications"]

        self.assertEqual(len(notifications), 1)
        self.assertEqual(
            notifications[0]["notification_type"], "profile_update_reminder"
        )

    def test_pagination_uses_global_shape(self):
        """
        Pagination uses the global limit/offset shape.
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url, {"limit": 1, "offset": 0})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()

        self.assertIn("pagination", payload)
        self.assertEqual(payload["pagination"]["count"], 2)
        self.assertEqual(payload["pagination"]["limit"], 1)
        self.assertEqual(payload["pagination"]["offset"], 0)
        self.assertEqual(payload["pagination"]["next"], 2)
        self.assertIsNone(payload["pagination"]["previous"])
        self.assertEqual(len(payload["data"]["notifications"]), 1)

    @patch(
        "apps.notifications.services.application_notification_service.NotificationService.send_to_user"
    )
    def test_new_notification_invalidates_cached_list(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.client.force_authenticate(user=self.user)

        first_response = self.client.get(self.url, {"limit": 20, "offset": 0})
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(first_response.json()["data"]["notifications"]), 2)

        ApplicationNotificationService.create_user_notification(
            user=self.user,
            title="Fresh",
            message="Fresh notification",
            notification_type=Notification.NotificationType.PLATFORM_ANNOUNCEMENT,
            data={"url": "https://app.workxplorer.uz/en/dashboard/chat?chat=1"},
        )

        second_response = self.client.get(self.url, {"limit": 20, "offset": 0})
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second_response.json()["data"]["notifications"]), 3)


class SendNotificationAPITests(APITestCase):
    """
    Test suite for SendNotificationAPIView.
    Verifies permissions, payload validation,
    device checks, and successful push send.
    """

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("send-notification")

        # Users
        self.admin_user = CustomUser.objects.create_superuser(
            email="admin@test.com", password="testpass123"
        )
        self.normal_user = CustomUser.objects.create_user(
            email="user@test.com", password="testpass123"
        )

        # Device for admin
        self.device = FCMDevice.objects.create(
            user=self.admin_user,
            registration_id="fake_token_123",
            active=True,
        )

        # Valid request payload
        self.valid_payload = {
            "title": "Important Update",
            "message": "Please check the latest updates in your app.",
            "sent_to_all": True,
            "data": {"extra": "info"},
        }

    def test_unauthenticated_user_cannot_send(self):
        """
        Unauthenticated user cannot send notifications
        """
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_user_cannot_send(self):
        """
        Non-admin users are forbidden
        """
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_required_fields(self):
        """
        Validation error if required fields are missing
        """
        self.client.force_authenticate(user=self.admin_user)
        payload = {"title": "Only title"}
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Title, message, and sent_to_all", response.json()["error"]["message"])

    def test_no_active_devices(self):
        """
        Should fail if no active devices exist
        """
        self.device.active = False
        self.device.save()

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No active devices", response.json()["error"]["message"])
    
    @patch("apps.notifications.services.notification_service.messaging.send")
    def test_send_notification_successfully(self, mock_send):
        """
        Successful notification send with mocked FCM
        """
        mock_send.return_value = "mock_message_id"

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        data = payload["data"]

        self.assertEqual(data["success_count"], 1)
        self.assertEqual(data["failure_count"], 0)
        self.assertEqual(data["sent_count"], 1)
        self.assertIn("notification_id", data)

        notification = Notification.objects.get(id=data["notification_id"])
        self.assertEqual(notification.title, "Important Update")
        self.assertEqual(notification.sent_count, 1)


class RegisterDeviceAPITests(APITestCase):
    """
    Test suite for RegisterDeviceAPIView.
    Handles device registration and updates.
    """

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("register-device")

        self.user = CustomUser.objects.create_user(
            email="user@test.com",
            password="testpass123",
        )

        self.valid_payload = {
            "registration_id": "fake_device_token_123",
            "type": "android",
        }

    def test_unauthenticated_user_cannot_register(self):
        """
        Unauthenticated user should get 401
        """
        response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_registration_id(self):
        """
        Registration requires registration_id
        """
        self.client.force_authenticate(user=self.user)
        payload = {"type": "ios"}
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("registration_id is required.", response.json()["error"]["message"])

    def test_register_new_device(self):
        """
        Register a new device for a user
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["message"], "Device registered successfully.")
        device = FCMDevice.objects.get(id=data["data"]["device_id"])
        self.assertEqual(device.user, self.user)
        self.assertTrue(device.active)

    def test_update_existing_device(self):
        """
        Update existing device registration
        """
        device = FCMDevice.objects.create(
            registration_id="fake_device_token_123",
            type="android",
            user=self.user,
            active=False,
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, self.valid_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["data"]["device_id"], device.id)

        device.refresh_from_db()
        self.assertTrue(device.active)


class NotificationMarkAsReadAPITests(APITestCase):
    """
    Test suite for NotificationMarkAsReadAPIView.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email="user@test.com",
            password="testpass123",
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@test.com",
            password="testpass123",
        )

        # Create notification + recipient link
        self.notification = Notification.objects.create(
            title="Test Notification",
            message="Hello World!",
        )
        self.recipient = NotificationRecipient.objects.create(
            notification=self.notification,
            user=self.user,
            is_read=False,
        )

        self.url = reverse(
            "mark-as-read", kwargs={"notification_id": self.notification.id}
        )

    def test_unauthenticated_user_cannot_mark_as_read(self):
        """
        401 if not authenticated
        """
        response = self.client.patch(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_mark_own_notification_as_read(self):
        """
        User can mark their own notification as read
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["message"], "Notification marked as read")

        self.recipient.refresh_from_db()
        self.assertTrue(self.recipient.is_read)
        self.assertIsNotNone(self.recipient.read_at)

    def test_user_cannot_mark_others_notification_as_read(self):
        """
        User should not mark other's notifications
        """
        self.client.force_authenticate(user=self.other_user)
        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Notification not found", response.json()["error"]["message"])


class NotificationBulkMarkAsReadAPITests(APITestCase):
    """
    Test suite for NotificationBulkMarkAsReadAPIView.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email="user@test.com",
            password="testpass123",
        )

        # Create notifications + recipients
        self.notification1 = Notification.objects.create(title="N1", message="Hello 1")
        self.notification2 = Notification.objects.create(title="N2", message="Hello 2")
        self.notification3 = Notification.objects.create(title="N3", message="Hello 3")

        self.rec1 = NotificationRecipient.objects.create(
            notification=self.notification1, user=self.user, is_read=False
        )
        self.rec2 = NotificationRecipient.objects.create(
            notification=self.notification2, user=self.user, is_read=False
        )
        self.rec3 = NotificationRecipient.objects.create(
            notification=self.notification3, user=self.user, is_read=True
        )

        self.url = reverse("bulk-mark-as-read")

    def test_unauthenticated_user_cannot_bulk_mark_as_read(self):
        """
        Unauthenticated users should get 401
        """
        response = self.client.patch(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bulk_mark_as_read_successfully(self):
        """
        Bulk mark all unread notifications
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["data"]["updated_count"], 2)
        self.assertIn("2 notifications marked as read", data["message"])

        # Ensure all are now read
        self.rec1.refresh_from_db()
        self.rec2.refresh_from_db()
        self.rec3.refresh_from_db()
        self.assertTrue(self.rec1.is_read)
        self.assertTrue(self.rec2.is_read)
        self.assertTrue(self.rec3.is_read)

    def test_bulk_mark_as_read_when_no_unread(self):
        """
        If all are already read, updated_count should be 0
        """
        NotificationRecipient.objects.filter(user=self.user).update(
            is_read=True, read_at=timezone.now()
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["data"]["updated_count"], 0)
        self.assertIn("0 notifications marked as read", data["message"])


class SendNotificationToUserAPITests(APITestCase):
    """
    Test suite for SendNotificationToUserAPIView.
    Verifies:
    - Only admins can send
    - Required fields validated
    - UUID format checked
    - Type validation
    - Device existence
    - Successful send
    """

    def setUp(self):
        self.client = APIClient()
        self.admin_user = CustomUser.objects.create_superuser(
            email="admin@test.com",
            password="adminpass123",
        )
        self.normal_user = CustomUser.objects.create_user(
            email="user@test.com",
            password="userpass123",
        )
        self.url = reverse("send-notification-to-user")

        self.payload = {
            "user_id": str(self.normal_user.id),
            "title": "Hello",
            "message": "Test notification",
            "notification_type": Notification.NotificationType.PLATFORM_ANNOUNCEMENT,
            "data": {"foo": "bar"},
        }

    def test_unauthenticated_user_cannot_access(self):
        """
        401 if unauthenticated
        """
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_user_forbidden(self):
        """
        403 if not admin
        """
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_required_fields(self):
        """
        400 if missing title/message/sent_to_all
        """
        self.client.force_authenticate(user=self.admin_user)
        payload = {"user_id": str(self.normal_user.id)}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("required", response.json()["error"]["message"])

    def test_invalid_uuid(self):
        """
        400 if user_id is not valid UUID
        """
        self.client.force_authenticate(user=self.admin_user)
        payload = self.payload.copy()
        payload["user_id"] = "not-a-uuid"
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid user_id format", response.json()["error"]["message"])

    def test_invalid_notification_type(self):
        """
        400 if notification_type is invalid
        """
        self.client.force_authenticate(user=self.admin_user)
        payload = self.payload.copy()
        payload["notification_type"] = "invalid_type"
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid notification_type", response.json()["error"]["message"])

    def test_user_not_found(self):
        """
        404 if user_id does not exist
        """
        self.client.force_authenticate(user=self.admin_user)
        payload = self.payload.copy()
        payload["user_id"] = str(uuid.uuid4())
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("User not found", response.json()["error"]["message"])

    def test_no_active_devices(self):
        """
        400 if no active devices exist
        """
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No active devices", response.json()["error"]["message"])

    @patch("apps.notifications.services.notification_service.messaging.send")
    def test_send_notification_success(self, mock_send):
        """
        Successful send with active device + mocked FCM
        """
        self.client.force_authenticate(user=self.admin_user)

        # Create device for normal user
        FCMDevice.objects.create(
            user=self.normal_user,
            registration_id="test_device_token",
            type="android",
            active=True,
        )

        mock_send.return_value = "mock_message_id"

        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        data = payload["data"]

        self.assertTrue(data["push_notification_sent"])
        self.assertGreaterEqual(data["success_count"], 0)

