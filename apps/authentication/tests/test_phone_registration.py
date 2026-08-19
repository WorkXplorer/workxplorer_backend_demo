from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate


class PhoneRegistrationTests(APITestCase):
    def setUp(self):
        self.send_url = reverse("phone-register-send-otp")
        self.verify_url = reverse("phone-register-verify")

    @patch("apps.authentication.views.phone_registration.PhoneOtpService.send")
    def test_send_otp_unauthenticated_ok(self, mock_send):
        response = self.client.post(self.send_url, {"phone": "901234567"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        mock_send.assert_called_once_with("+998901234567", language="uz")

    def test_send_otp_rejects_phone_already_registered(self):
        from django.utils import timezone

        existing = Candidate.objects.create_user(email="existing@example.com", password="pw", is_candidate=True)
        existing.phone = "+998901234567"
        existing.phone_verified_at = timezone.now()
        existing.save(update_fields=["phone", "phone_verified_at"])

        response = self.client.post(self.send_url, {"phone": "901234567"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    @patch("apps.authentication.views.phone_registration.PhoneOtpService.verify", return_value=True)
    def test_verify_creates_account(self, mock_verify):
        response = self.client.post(
            self.verify_url,
            {
                "phone": "901234567",
                "code": "123456",
                "email": "newuser@example.com",
                "password": "StrongPass!2345",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())

        user = Candidate.objects.get(email="newuser@example.com")
        self.assertEqual(user.phone, "+998901234567")
        self.assertIsNotNone(user.phone_verified_at)
        self.assertTrue(user.check_password("StrongPass!2345"))
        self.assertTrue(user.is_candidate)

    @patch("apps.authentication.views.phone_registration.PhoneOtpService.verify", return_value=False)
    def test_verify_rejects_wrong_code(self, mock_verify):
        response = self.client.post(
            self.verify_url,
            {"phone": "901234567", "code": "000000", "email": "x@example.com", "password": "StrongPass!2345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Candidate.objects.filter(email="x@example.com").exists())

    def test_verify_rejects_weak_password(self):
        response = self.client.post(
            self.verify_url,
            {"phone": "901234567", "code": "123456", "email": "weak@example.com", "password": "123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_rejects_duplicate_email(self):
        Candidate.objects.create_user(email="dupe@example.com", password="pw", is_candidate=True)

        response = self.client.post(
            self.verify_url,
            {"phone": "901234567", "code": "123456", "email": "dupe@example.com", "password": "StrongPass!2345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    @patch("apps.authentication.views.phone_registration.PhoneOtpService.verify", return_value=True)
    def test_new_account_can_log_in_by_phone_or_email(self, mock_verify):
        self.client.post(
            self.verify_url,
            {"phone": "901234567", "code": "123456", "email": "loginme@example.com", "password": "StrongPass!2345"},
            format="json",
        )

        by_phone = self.client.post(
            reverse("cookie-login"),
            {"phone": "901234567", "password": "StrongPass!2345", "user_type": "candidate"},
            format="json",
        )
        self.assertEqual(by_phone.status_code, status.HTTP_200_OK, by_phone.json())

        by_email = self.client.post(
            reverse("cookie-login"),
            {"email": "loginme@example.com", "password": "StrongPass!2345", "user_type": "candidate"},
            format="json",
        )
        self.assertEqual(by_email.status_code, status.HTTP_200_OK, by_email.json())
