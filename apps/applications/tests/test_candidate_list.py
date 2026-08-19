from django.utils import timezone
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class CandidateApplicationsListViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Test Company",
            tin="123456789",
        )
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com", password="testpass123", is_recruiter=True
        )
        cls.candidate = Candidate.objects.create_user(
            email="test_candidate@example.com",
            password="testpass123",
        )
        cls.vacancy = Vacancy.objects.create(
            title="Software Engineer",
            company_id=cls.company.id,
            created_by_id=cls.recruiter.id,
        )
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
        )
        cls.url = reverse("applications-list")

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_only_candidate_applications(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["pagination"]["count"], 1)
        self.assertEqual(len(data["data"]), 1)

        app = data["data"][0]
        self.assertEqual(app["title"], "Software Engineer")
        self.assertEqual(app["company_name"], "Test Company")
        self.assertEqual(app["status_display"], "Applied")

    def test_non_candidate_user_gets_empty_queryset(self):
        user = Candidate.objects.create_user(
            email="normal@example.com",
            password="testpass123",
            is_candidate=False,
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["pagination"]["count"], 0)
        self.assertEqual(len(data["data"]), 0)

    def test_multiple_applications_ordering(self):
        vacancy2 = Vacancy.objects.create(
            title="Backend Developer",
            company_id=self.company.id,
            created_by_id=self.recruiter.id,
        )
        JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=vacancy2,
            applied_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["pagination"]["count"], 2)
        self.assertEqual(len(data["data"]), 2)
