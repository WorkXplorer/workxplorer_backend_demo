from types import SimpleNamespace
from unittest.mock import patch
from fcm_django.models import FCMDevice

from rest_framework.test import APITestCase
from apps.notifications.services import NotificationService
from apps.authentication.models import CustomUser


class NotificationServiceTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="service@test.com",
            password="testpass123",
        )
        self.device_one = FCMDevice.objects.create(
            user=self.user,
            registration_id="device-token-1",
            type="android",
            active=True,
        )
        self.device_two = FCMDevice.objects.create(
            user=self.user,
            registration_id="device-token-2",
            type="android",
            active=True,
        )

    @patch("apps.notifications.services.notification_service.messaging.send_multicast")
    @patch(
        "apps.notifications.services.notification_service.messaging.send_each_for_multicast"
    )
    def test_send_to_devices_uses_send_each_for_multicast(
            self, mock_send_each_for_multicast, mock_send_multicast
    ):
        mock_send_each_for_multicast.return_value = SimpleNamespace(
            success_count=2,
            failure_count=0,
            responses=[
                SimpleNamespace(success=True, exception=None),
                SimpleNamespace(success=True, exception=None),
            ],
        )

        result = NotificationService.send_to_devices(
            [self.device_one, self.device_two],
            "Title",
            "Body",
            {"kind": "test"},
        )

        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failure_count"], 0)
        mock_send_each_for_multicast.assert_called_once()
        mock_send_multicast.assert_not_called()

    @patch("apps.notifications.services.notification_service.messaging.send")
    def test_send_to_device_deactivates_invalid_token(self, mock_send):
        mock_send.side_effect = Exception("NotRegistered")

        result = NotificationService.send_to_device(
            self.device_one,
            "Title",
            "Body",
            {"kind": "test"},
        )

        self.assertFalse(result)
        self.device_one.refresh_from_db()
        self.assertFalse(self.device_one.active)
