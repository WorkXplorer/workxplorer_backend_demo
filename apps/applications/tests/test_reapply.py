from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class ReapplyToVacancyViewTests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        self.candidate = Candidate.objects.create_user(
            email="candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        self.company = Company.objects.create(name="Withdraw Test Co", tin="222333444")
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=self.company,
        )
        self.vacancy = Vacancy.objects.create(
            title="Backend Developer",
            created_by=self.recruiter,
            company=self.recruiter.company,
        )
        self.application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status=ApplicationStatus.WITHDRAWN,
        )
        self.url = reverse(
            "reapply-to-vacancy",
            kwargs={"application_id": self.application.id},
        )

    def test_successful_reapplication(self):
        self.client.force_authenticate(user=self.candidate)

        response = self.client.put(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["data"]["status"], ApplicationStatus.APPLIED)

        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPLIED)

    def test_reapply_not_allowed_for_invalid_status(self):
        self.application.status = ApplicationStatus.APPLIED
        self.application.save()

        self.client.force_authenticate(user=self.candidate)
        response = self.client.put(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot reapply", str(response.json()))

    def test_non_candidate_cannot_reapply(self):
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.put(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_cannot_reapply(self):
        response = self.client.put(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
