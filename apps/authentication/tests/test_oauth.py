from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from apps.authentication.models.candidate import Candidate
from apps.authentication.models.recruiter import Recruiter, Company

User = get_user_model()

VALID_ID_INFO = {
    "email": "oauth_user@example.com",
    "email_verified": True,
    "sub": "google-uid-12345",
    "name": "Test User",
}


class GoogleOAuthCandidateViewTests(APITestCase):
    """
    Test suite for POST /auth/google/

    Covers: new candidate creation, existing candidate login, wrong user type,
    missing credential, invalid token, and unverified email.
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("google-oauth-candidate")

        # Pre-existing candidate
        cls.existing_candidate = Candidate(
            email="existing_candidate@example.com",
            is_active=True,
            is_candidate=True,
        )
        cls.existing_candidate.set_unusable_password()
        cls.existing_candidate.save()

        # Pre-existing recruiter (non-candidate)
        company = Company.objects.create(
            name="Test Company",
            tin="123456789",
        )
        cls.recruiter_user = Recruiter(
            email="recruiter@example.com",
            is_active=True,
            is_recruiter=True,
            company=company,
        )
        cls.recruiter_user.set_unusable_password()
        cls.recruiter_user.save()

    # -------------------------------------------------------------------------
    # Happy path
    # -------------------------------------------------------------------------

    @patch("apps.authentication.views.oauth_views.id_token.verify_oauth2_token")
    @patch("apps.authentication.views.oauth_views.ConsentService.create_consents_for_entity")
    def test_new_candidate_created(self, mock_consent, mock_verify):
        """Valid credential for a new email should create a Candidate and return 200."""
        mock_verify.return_value = VALID_ID_INFO
        mock_consent.return_value = []

        response = self.client.post(
            self.url, {"credential": "fake-google-token"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("access_token", response.cookies)
        self.assertIn("refresh_token", response.cookies)

        candidate = Candidate.objects.filter(email=VALID_ID_INFO["email"]).first()
        self.assertIsNotNone(candidate)
        self.assertFalse(candidate.has_usable_password())
        self.assertTrue(candidate.is_candidate)

    @patch("apps.authentication.views.oauth_views.id_token.verify_oauth2_token")
    @patch("apps.authentication.views.oauth_views.ConsentService.create_consents_for_entity")
    def test_existing_candidate_logs_in(self, mock_consent, mock_verify):
        """Valid credential for an existing candidate email should log them in (no new user)."""
        mock_verify.return_value = {
            "email": self.existing_candidate.email,
            "email_verified": True,
        }

        user_count_before = User.objects.count()
        response = self.client.post(
            self.url, {"credential": "fake-google-token"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("access_token", response.cookies)
        # No new user was created
        self.assertEqual(User.objects.count(), user_count_before)
        mock_consent.assert_not_called()

    # -------------------------------------------------------------------------
    # Error cases
    # -------------------------------------------------------------------------

    @patch("apps.authentication.views.oauth_views.id_token.verify_oauth2_token")
    def test_existing_non_candidate_user_rejected(self, mock_verify):
        """Valid credential for a recruiter/admin email should return 403."""
        mock_verify.return_value = {
            "email": self.recruiter_user.email,
            "email_verified": True,
        }

        response = self.client.post(
            self.url, {"credential": "fake-google-token"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "WRONG_USER_TYPE")

    def test_missing_credential(self):
        """Request without 'credential' key should return 400."""
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "MISSING_CREDENTIAL")

    @patch("apps.authentication.views.oauth_views.id_token.verify_oauth2_token")
    def test_invalid_google_token(self, mock_verify):
        """Token that fails Google verification should return 401."""
        mock_verify.side_effect = ValueError("Token is invalid or expired")

        response = self.client.post(
            self.url, {"credential": "bad-token"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "INVALID_GOOGLE_TOKEN")

    @patch("apps.authentication.views.oauth_views.id_token.verify_oauth2_token")
    def test_unverified_email(self, mock_verify):
        """Google account with email_verified=False should return 400."""
        mock_verify.return_value = {
            "email": "unverified@example.com",
            "email_verified": False,
        }

        response = self.client.post(
            self.url, {"credential": "fake-token"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "EMAIL_NOT_VERIFIED")
