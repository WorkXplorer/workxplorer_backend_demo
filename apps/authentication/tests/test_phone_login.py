from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate

MOBILE_KEY = "test-mobile-app-key"


class PhoneVerificationViewTests(APITestCase):
    def setUp(self):
        self.candidate = Candidate.objects.create_user(
            email="phone-candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        self.client.force_authenticate(user=self.candidate)
        self.send_url = reverse("phone-send-otp")
        self.verify_url = reverse("phone-verify-otp")

    @patch("apps.authentication.views.phone_verification.PhoneOtpService.send")
    def test_send_otp_normalizes_and_sends(self, mock_send):
        response = self.client.post(self.send_url, {"phone": "901234567"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        mock_send.assert_called_once_with("+998901234567", language="uz")

    def test_send_otp_rejects_invalid_phone(self):
        response = self.client.post(self.send_url, {"phone": "123"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_otp_rejects_phone_already_verified_on_another_account(self):
        other = Candidate.objects.create_user(
            email="other@example.com", password="pw", is_candidate=True
        )
        other.phone = "+998901234567"
        other.phone_verified_at = timezone.now()
        other.save(update_fields=["phone", "phone_verified_at"])

        response = self.client.post(self.send_url, {"phone": "901234567"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    @patch("apps.authentication.views.phone_verification.PhoneOtpService.verify", return_value=True)
    def test_verify_otp_marks_phone_verified(self, mock_verify):
        response = self.client.post(
            self.verify_url, {"phone": "901234567", "code": "123456"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.phone, "+998901234567")
        self.assertIsNotNone(self.candidate.phone_verified_at)

    @patch("apps.authentication.views.phone_verification.PhoneOtpService.verify", return_value=False)
    def test_verify_otp_rejects_wrong_code(self, mock_verify):
        response = self.client.post(
            self.verify_url, {"phone": "901234567", "code": "000000"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.phone_verified_at)


class PhonePasswordLoginTests(APITestCase):
    def setUp(self):
        self.candidate = Candidate.objects.create_user(
            email="verified-candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate.phone = "+998901234567"
        self.candidate.phone_verified_at = timezone.now()
        self.candidate.save(update_fields=["phone", "phone_verified_at"])

    def test_web_login_with_verified_phone(self):
        response = self.client.post(
            reverse("cookie-login"),
            {"phone": "901234567", "password": "testpass123", "user_type": "candidate"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertEqual(
            response.json()["data"]["user"]["email"], "verified-candidate@example.com"
        )
        self.assertIn("access_token", response.cookies)

    def test_web_login_with_unverified_phone_is_rejected(self):
        unverified = Candidate.objects.create_user(
            email="unverified@example.com", password="testpass123", is_candidate=True
        )
        unverified.phone = "+998907654321"
        unverified.save(update_fields=["phone"])  # no phone_verified_at

        response = self.client.post(
            reverse("cookie-login"),
            {"phone": "907654321", "password": "testpass123", "user_type": "candidate"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_web_login_without_email_or_phone_is_rejected(self):
        response = self.client.post(
            reverse("cookie-login"),
            {"password": "testpass123", "user_type": "candidate"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
    def test_mobile_login_with_verified_phone_returns_tokens_in_body(self):
        response = self.client.post(
            reverse("mobile-login"),
            {
                "phone": "901234567",
                "password": "testpass123",
                "device": {"device_id": "device-1", "platform": "ios"},
            },
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertEqual(
            response.json()["data"]["user"]["email"], "verified-candidate@example.com"
        )
        self.assertIn("access_token", response.json()["data"])
