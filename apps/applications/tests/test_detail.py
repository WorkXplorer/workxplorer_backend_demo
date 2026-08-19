from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class ApplicationDetailViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Detail Test Company",
            tin="111222333",
        )
        cls.recruiter = Recruiter.objects.create_user(
            email="detail_recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        cls.candidate = Candidate.objects.create_user(
            email="detail_candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.vacancy = Vacancy.objects.create(
            title="ML Engineer",
            company=cls.company,
            created_by=cls.recruiter,
        )
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
        )
        cls.url = reverse(
            "application-detail", kwargs={"application_id": cls.application.id}
        )

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_candidate_can_view_own_application(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["data"]["id"], str(self.application.id))
        self.assertEqual(data["data"]["vacancy_title"], "ML Engineer")

    def test_candidate_cannot_view_others_application(self):
        other_candidate = Candidate.objects.create_user(
            email="other_cand@example.com",
            password="testpass123",
            is_candidate=True,
        )
        self.client.force_authenticate(user=other_candidate)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_recruiter_can_view_applications_to_own_company(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_recruiter_cannot_view_applications_of_other_company(self):
        other_company = Company.objects.create(name="OtherCo", tin="444555666")
        other_recruiter = Recruiter.objects.create_user(
            email="other_recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=other_company,
        )
        self.client.force_authenticate(user=other_recruiter)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_application_id_returns_404(self):
        self.client.force_authenticate(user=self.candidate)
        url = reverse(
            "application-detail",
            kwargs={"application_id": "11111111-1111-1111-1111-111111111111"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
