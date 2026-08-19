from django.urls import reverse
from django.test import override_settings
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.notifications.models import Notification, NotificationRecipient
from apps.profiles.models import CandidateProfile
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


@override_settings(FRONTEND_URL="https://app.workxplorer.uz")
class OfferResponseNotificationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Offer Notify Co", tin="333444555")
        cls.recruiter = Recruiter.objects.create_user(
            email="offer_recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
            preferred_language="en",
        )
        cls.candidate = Candidate.objects.create_user(
            email="offer_candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=cls.candidate,
            full_name="Offer Candidate",
        )
        cls.vacancy = Vacancy.objects.create(
            title="Product Manager",
            created_by=cls.recruiter,
            company=cls.company,
        )

    def setUp(self):
        self.application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status=ApplicationStatus.OFFERED,
        )
        self.accept_url = reverse(
            "accept-offer",
            kwargs={"application_id": self.application.id},
        )
        self.reject_url = reverse(
            "reject-offer",
            kwargs={"application_id": self.application.id},
        )

    @patch(
        "apps.notifications.services.application_notification_service.NotificationService.send_to_user"
    )
    def test_accept_offer_creates_recruiter_notification(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.client.force_authenticate(user=self.candidate)
        response = self.client.put(self.accept_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.APPLICATION_ACCEPTED
        )
        recipient = NotificationRecipient.objects.get(notification=notification)

        self.assertEqual(recipient.user_id, self.recruiter.id)
        self.assertEqual(
            notification.message,
            "Offer Candidate accepted the offer for Product Manager.",
        )
        self.assertEqual(
            notification.data["url"],
            f"https://app.workxplorer.uz/en/dashboard/chat?chat={self.application.conversation.id}",
        )

    @patch(
        "apps.notifications.services.application_notification_service.NotificationService.send_to_user"
    )
    def test_reject_offer_creates_recruiter_notification(self, mock_send):
        mock_send.return_value = {
            "success": True,
            "devices_count": 1,
            "success_count": 1,
        }

        self.client.force_authenticate(user=self.candidate)
        response = self.client.put(self.reject_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.APPLICATION_REJECTED
        )
        recipient = NotificationRecipient.objects.get(notification=notification)

        self.assertEqual(recipient.user_id, self.recruiter.id)
        self.assertEqual(
            notification.message,
            "Offer Candidate rejected the offer for Product Manager.",
        )
