from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class WithdrawApplicationViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Withdraw Test Co", tin="222333444")
        cls.recruiter = Recruiter.objects.create_user(
            email="withdraw_recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        cls.candidate = Candidate.objects.create_user(
            email="withdraw_candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.vacancy = Vacancy.objects.create(
            title="Frontend Developer",
            company=cls.company,
            created_by=cls.recruiter,
        )
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=ApplicationStatus.APPLIED,
        )
        cls.url = reverse(
            "withdraw-application", kwargs={"application_id": cls.application.id}
        )

    def test_requires_authentication(self):
        response = self.client.patch(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_candidates_can_withdraw(self):
        user = Candidate.objects.create_user(
            email="not_candidate@example.com",
            password="testpass123",
            is_candidate=False,
        )
        self.client.force_authenticate(user=user)
        response = self.client.patch(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_can_withdraw_successfully(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.patch(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["message"], "Application withdrawn successfully")
        self.assertEqual(data["data"]["status_display"], "Withdrawn")

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.WITHDRAWN)

    def test_candidate_cannot_withdraw_other_candidate_application(self):
        other_candidate = Candidate.objects.create_user(
            email="other_candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        self.client.force_authenticate(user=other_candidate)
        response = self.client.patch(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_withdraw_if_status_disallows(self):
        self.application.status = ApplicationStatus.REJECTED
        self.application.save()

        self.client.force_authenticate(user=self.candidate)
        response = self.client.patch(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.json()["error"]["field_errors"])

    def test_candidate_can_withdraw_from_ai_failed(self):
        self.application.status = ApplicationStatus.AI_FAILED
        self.application.save()

        self.client.force_authenticate(user=self.candidate)
        response = self.client.patch(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.WITHDRAWN)
