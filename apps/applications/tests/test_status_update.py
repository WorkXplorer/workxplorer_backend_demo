from django.urls import reverse
from django.utils import timezone
from django.test import override_settings
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.notifications.models import Notification, NotificationRecipient
from apps.profiles.models import CandidateProfile, RecruiterProfile
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class UpdateApplicationStatusViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company1 = Company.objects.create(name="Company 1", tin="111111111")
        cls.company2 = Company.objects.create(name="Company 2", tin="222222222")

        cls._admin_recruiter = Recruiter.objects.create_user(
            email="admin@company1.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company1,
        )
        cls.admin_recruiter = RecruiterProfile.objects.create(
            recruiter=cls._admin_recruiter,
            full_name="Joe Alison",
            level="Admin",
        )

        cls._recruiter_recruiter = Recruiter.objects.create_user(
            email="recruiter@company1.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company1,
        )
        cls.recruiter_recruiter = RecruiterProfile.objects.create(
            recruiter=cls._recruiter_recruiter,
            full_name="Kevin Burger",
            level="Recruiter",
        )

        cls._other_recruiter = Recruiter.objects.create_user(
            email="other@company2.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company2,
        )
        cls.other_recruiter = RecruiterProfile.objects.create(
            recruiter=cls._other_recruiter,
            full_name="Other Alex",
            level="Admin",
        )

        cls.candidate = Candidate.objects.create_user(
            email="candidate@company1.com",
            password="testpass123",
            is_candidate=True,
            preferred_language="ru",
        )
        CandidateProfile.objects.create(
            candidate=cls.candidate,
            full_name="Candidate One",
        )

        cls.vacancy = Vacancy.objects.create(
            title="QA Engineer",
            company=cls.company1,
            created_by=cls._admin_recruiter,
        )

        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=ApplicationStatus.APPLIED,
        )

        cls.url = reverse(
            "update-application-status",
            kwargs={"application_id": cls.application.id},
        )

    def test_requires_authentication(self):
        response = self.client.patch(
            self.url, {"status": ApplicationStatus.REJECTED}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_admin_and_manager_can_update(self):
        self.client.force_authenticate(user=self._recruiter_recruiter)
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.REJECTED, "recruiter_notes": "Test note"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self._admin_recruiter)
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.REJECTED, "recruiter_notes": "Test note"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cannot_update_other_company_application(self):
        self.client.force_authenticate(user=self._other_recruiter)
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.REJECTED, "recruiter_notes": "Test note"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_application_id_returns_404(self):
        self.client.force_authenticate(user=self._admin_recruiter)
        url = reverse(
            "update-application-status",
            kwargs={"application_id": "11111111-1111-1111-1111-111111111111"},
        )
        response = self.client.patch(
            url,
            {"status": ApplicationStatus.REJECTED, "recruiter_notes": "Test note"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_audit_trail_and_notes(self):
        self.client.force_authenticate(user=self._admin_recruiter)
        notes = "Candidate did not pass technical interview"
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.REJECTED, "recruiter_notes": notes},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertIn(notes, self.application.recruiter_notes)
        self.assertEqual(self.application.last_updated_by, self._admin_recruiter)

    @override_settings(FRONTEND_URL="https://app.workxplorer.uz")
    @patch(
        "apps.notifications.services.application_notification_service.NotificationService.send_to_user"
    )
    def test_status_update_creates_candidate_notification(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.client.force_authenticate(user=self._admin_recruiter)
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.OFFERED, "recruiter_notes": "Offer sent"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.APPLICATION_OFFERED
        )
        recipient = NotificationRecipient.objects.get(notification=notification)

        self.assertEqual(recipient.user_id, self.candidate.id)
        self.assertEqual(notification.title, "Application status updated")
        self.assertEqual(notification.data["conversation_id"], str(self.application.conversation.id))
        self.assertEqual(
            notification.data["url"],
            f"https://app.workxplorer.uz/ru/dashboard/chat?chat={self.application.conversation.id}",
        )
