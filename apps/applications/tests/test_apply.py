from django.urls import reverse
from django.utils import timezone
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.notifications.models import Notification, NotificationRecipient
from apps.profiles.models import CandidateProfile
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter

User = get_user_model()


class ApplyToVacancyViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Apply Test Company",
            tin="987654321",
        )
        cls.recruiter = Recruiter.objects.create_user(
            email="apply_recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
        )
        cls.candidate = Candidate.objects.create_user(
            email="apply_candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=cls.candidate,
            full_name="Applied Candidate",
        )
        cls.vacancy = Vacancy.objects.create(
            title="Data Scientist",
            company_id=cls.company.id,
            created_by_id=cls.recruiter.id,
        )
        cls.url = reverse("apply-to-vacancy")

    def test_requires_authentication(self):
        response = self.client.post(
            self.url, {"vacancy": self.vacancy.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_candidates_can_apply(self):
        user = User.objects.create_user(
            email="not_candidate@example.com",
            password="testpass123",
            is_candidate=False,
        )
        self.client.force_authenticate(user=user)
        response = self.client.post(
            self.url, {"vacancy_id": self.vacancy.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", response.json())

    def test_successful_application(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(
            self.url, {"vacancy_id": self.vacancy.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.json()
        self.assertEqual(data["message"], "Application submitted successfully")
        self.assertEqual(data["data"]["vacancy"]["title"], self.vacancy.title)
        self.assertEqual(data["data"]["candidate"]["email"], self.candidate.email)

        self.assertTrue(
            JobApplication.objects.filter(
                candidate=self.candidate, vacancy=self.vacancy
            ).exists()
        )

    @override_settings(FRONTEND_URL="https://app.workxplorer.uz")
    @patch(
        "apps.notifications.services.application_notification_service.NotificationService.send_to_user"
    )
    def test_successful_application_creates_recruiter_notification(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }
        self.recruiter.preferred_language = "en"
        self.recruiter.save(update_fields=["preferred_language"])

        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(
            self.url,
            {"vacancy_id": self.vacancy.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.APPLICATION_APPLIED
        )
        recipient = NotificationRecipient.objects.get(notification=notification)

        self.assertEqual(recipient.user_id, self.recruiter.id)
        self.assertEqual(notification.message, "Applied Candidate applied to Data Scientist.")
        self.assertEqual(
            notification.data["url"],
            f"https://app.workxplorer.uz/en/dashboard/candidates?page=0&pageSize=20&vacancy_id={self.vacancy.id}",
        )

    @patch(
        "apps.notifications.services.application_notification_service.NotificationService.send_to_user"
    )
    def test_apply_query_count_stays_bounded(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.client.force_authenticate(user=self.candidate)
        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.post(
                self.url, {"vacancy_id": self.vacancy.id}, format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertLessEqual(
            len(captured_queries),
            25,
            msg=f"Unexpected query count: {len(captured_queries)}",
        )

    def test_duplicate_application_fails(self):
        JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            applied_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(
            self.url, {"vacancy_id": self.vacancy.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.json())

    def test_invalid_vacancy_id(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(self.url, {"vacancy_id": 9999}, format="json")
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND],
        )
