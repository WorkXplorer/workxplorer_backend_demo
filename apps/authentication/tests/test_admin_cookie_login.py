from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.general.models import EmailTemplate
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()


class AdminCookieTokenObtainPairViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("admin-cookie-login")
        self.staff_user = User.objects.create_user(
            email="staff@test.com",
            password="pass123",
            is_staff=True,
            is_active=True,
        )
        self.non_staff_user = User.objects.create_user(
            email="nonstaff@test.com",
            password="pass123",
            is_active=True,
        )

    def test_staff_user_without_candidate_or_recruiter_profile_can_log_in(self):
        response = self.client.post(
            self.url,
            {"email": "staff@test.com", "password": "pass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["access_token"]["httponly"])

    def test_non_staff_user_is_rejected(self):
        response = self.client.post(
            self.url,
            {"email": "nonstaff@test.com", "password": "pass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access_token", response.cookies)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            self.url,
            {"email": "staff@test.com", "password": "wrong-password"},
            format="json",
        )

        # simplejwt's TokenObtainPairSerializer raises AuthenticationFailed
        # (401) for bad credentials, not a plain ValidationError (400) —
        # same behavior as the sibling CookieTokenObtainPairView.
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_login_cookie_authorizes_admin_only_endpoint(self):
        EmailTemplate.objects.create(
            template_type="vacancy-newsletter",
            name="vacancy-newsletter",
            language="uz",
            subject="Subject",
            body=SimpleUploadedFile(
                "newsletter.html", b"<html></html>", content_type="text/html"
            ),
        )

        login_response = self.client.post(
            self.url,
            {"email": "staff@test.com", "password": "pass123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        campaign_response = self.client.post(
            reverse("manual-email-campaign-send"),
            {"template_type": "vacancy-newsletter", "emails": ["nobody@test.com"]},
            format="json",
        )

        # Authorized (IsAdminUser passes) — 200 even though the recipient
        # doesn't exist; a 401/403 here would mean the cookie didn't
        # authenticate as staff.
        self.assertEqual(campaign_response.status_code, status.HTTP_200_OK, campaign_response.json())
