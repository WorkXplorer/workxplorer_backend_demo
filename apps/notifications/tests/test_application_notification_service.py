from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.applications.models.applications import JobApplication
from apps.applications.models.choices import ApplicationStatus
from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.notifications.models import Notification, NotificationRecipient
from apps.notifications.services import ApplicationNotificationService
from apps.profiles.models import CandidateProfile
from apps.vacancies.models import Vacancy


@override_settings(FRONTEND_URL="https://app.workxplorer.uz/")
class ApplicationNotificationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Notify Co", tin="555666777")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
            preferred_language="en",
        )
        cls.candidate = Candidate.objects.create_user(
            email="candidate@example.com",
            password="testpass123",
            is_candidate=True,
            preferred_language="ru",
        )
        CandidateProfile.objects.create(
            candidate=cls.candidate,
            full_name="Test Candidate",
        )
        cls.vacancy = Vacancy.objects.create(
            title="Backend Engineer",
            company=cls.company,
            created_by=cls.recruiter,
        )
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            status=ApplicationStatus.APPLIED,
        )

    def test_build_frontend_url_respects_language_and_query_params(self):
        url = ApplicationNotificationService.build_frontend_url(
            "dashboard/chat",
            "ru",
            {"chat": "conversation-1", "page": 0},
        )

        self.assertEqual(
            url,
            "https://app.workxplorer.uz/ru/dashboard/chat?chat=conversation-1&page=0",
        )

    def test_get_user_language_falls_back_to_default(self):
        self.recruiter.preferred_language = "de"
        self.assertEqual(
            ApplicationNotificationService.get_user_language(self.recruiter),
            "uz",
        )

    @patch("apps.notifications.services.application_notification_service.NotificationService.send_to_user")
    def test_create_user_notification_persists_notification_and_recipient(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 2,
            "success_count": 1,
        }

        notification = ApplicationNotificationService.create_user_notification(
            user=self.recruiter,
            title="Title",
            message="Body",
            notification_type=Notification.NotificationType.APPLICATION_APPLIED,
            data={"url": "https://app.workxplorer.uz/en/dashboard/candidates"},
            created_by=self.candidate,
        )

        recipient = NotificationRecipient.objects.get(notification=notification)
        self.assertEqual(recipient.user_id, self.recruiter.id)
        self.assertEqual(notification.sent_count, 2)
        self.assertEqual(notification.success_count, 1)
        self.assertEqual(notification.failure_count, 1)

    @patch("apps.notifications.services.application_notification_service.NotificationService.send_to_user")
    def test_notify_recruiter_new_application_builds_expected_payload(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        notification = ApplicationNotificationService.notify_recruiter_new_application(
            self.application
        )

        self.assertIsNotNone(notification)
        self.assertEqual(
            notification.notification_type,
            Notification.NotificationType.APPLICATION_APPLIED,
        )
        self.assertEqual(
            notification.message,
            "Test Candidate applied to Backend Engineer.",
        )
        self.assertEqual(
            notification.data["url"],
            f"https://app.workxplorer.uz/en/dashboard/candidates?page=0&pageSize=20&vacancy_id={self.vacancy.id}",
        )

    @patch("apps.notifications.services.application_notification_service.NotificationService.send_to_user")
    def test_notify_candidate_status_updated_uses_chat_deeplink(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.application.status = ApplicationStatus.OFFERED
        self.application.last_updated_by = self.recruiter
        self.application.save(update_fields=["status", "last_updated_by"])

        notification = ApplicationNotificationService.notify_candidate_status_updated(
            self.application,
            old_status=ApplicationStatus.APPLIED,
            new_status=ApplicationStatus.OFFERED,
        )

        self.assertEqual(
            notification.notification_type,
            Notification.NotificationType.APPLICATION_OFFERED,
        )
        self.assertEqual(
            notification.data["status_display"],
            "Предложение сделано",
        )
        self.assertEqual(
            notification.data["conversation_id"],
            str(self.application.conversation.id),
        )
        self.assertEqual(
            notification.data["url"],
            f"https://app.workxplorer.uz/ru/dashboard/chat?chat={self.application.conversation.id}",
        )

    @patch("apps.notifications.services.application_notification_service.NotificationService.send_to_user")
    def test_notify_recruiter_offer_response_uses_candidate_name(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.application.status = ApplicationStatus.OFFER_ACCEPTED
        self.application.save(update_fields=["status"])

        notification = ApplicationNotificationService.notify_recruiter_offer_response(
            self.application
        )

        self.assertEqual(
            notification.notification_type,
            Notification.NotificationType.APPLICATION_ACCEPTED,
        )
        self.assertEqual(
            notification.message,
            "Test Candidate accepted the offer for Backend Engineer.",
        )
