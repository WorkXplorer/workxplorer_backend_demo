from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate, UserConsent
from apps.authentication.models.recruiter import Recruiter


class AccountDeleteViewTests(APITestCase):
    """
    Test suite for the self-service account deletion endpoint
    (DELETE /users/delete/me/).

    Covers: candidate-only access, confirmation and password checks,
    the actual data removal, and consent-record retention.
    """

    def setUp(self):
        self.url = reverse("account-delete")
        self.candidate = Candidate.objects.create_user(
            email="candidate@example.com", password="candidatepass123"
        )

    def test_requires_authentication(self):
        response = self.client.delete(self.url, {"confirm": True}, format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_recruiter_cannot_delete_own_account(self):
        recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com", password="recruiterpass123"
        )
        self.client.force_authenticate(user=recruiter)

        response = self.client.delete(
            self.url,
            {"confirm": True, "password": "recruiterpass123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Recruiter.objects.filter(pk=recruiter.pk).exists())

    def test_requires_confirmation_flag(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.delete(
            self.url, {"confirm": False, "password": "candidatepass123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Candidate.objects.filter(pk=self.candidate.pk).exists())

    def test_rejects_incorrect_password(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.delete(
            self.url, {"confirm": True, "password": "wrongpassword"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Candidate.objects.filter(pk=self.candidate.pk).exists())

    def test_requires_password_when_account_has_one(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.delete(self.url, {"confirm": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Candidate.objects.filter(pk=self.candidate.pk).exists())

    def test_candidate_deletes_own_account(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.delete(
            self.url,
            {"confirm": True, "password": "candidatepass123", "reason": "Found a job"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertFalse(Candidate.objects.filter(pk=self.candidate.pk).exists())

    def test_oauth_account_without_password_can_be_deleted(self):
        oauth_candidate = Candidate.objects.create_user(
            email="google@example.com", password=None
        )
        oauth_candidate.set_unusable_password()
        oauth_candidate.save()
        self.client.force_authenticate(user=oauth_candidate)

        response = self.client.delete(self.url, {"confirm": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Candidate.objects.filter(pk=oauth_candidate.pk).exists())

    def test_consent_records_are_kept_and_flagged(self):
        content_type = ContentType.objects.get_for_model(Candidate)
        consent = UserConsent.objects.create(
            content_type=content_type,
            object_id=str(self.candidate.pk),
            consent_type="privacy_policy",
            version="1.0",
            ip_address="127.0.0.1",
        )
        self.client.force_authenticate(user=self.candidate)

        response = self.client.delete(
            self.url, {"confirm": True, "password": "candidatepass123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        consent.refresh_from_db()
        self.assertTrue(consent.consenter_deleted)
        self.assertEqual(consent.consenter_email, "candidate@example.com")
