from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

SECRET = "test-secret-value"


class TriggerDailyReportViewTests(APITestCase):
    """The trigger endpoint is service-to-service, so auth is a shared secret."""

    def setUp(self):
        self.url = reverse("trigger-daily-report")

    def test_valid_secret_queues_the_report(self):
        with self.settings(TELEGRAM_BOT_API_SECRET=SECRET), patch(
            "django_rq.get_queue"
        ) as get_queue:
            get_queue.return_value.enqueue.return_value.id = "job-1"

            response = self.client.post(
                self.url, {}, format="json", HTTP_X_API_SECRET=SECRET
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["job_id"], "job-1")
        get_queue.return_value.enqueue.assert_called_once()
        self.assertIsNone(
            get_queue.return_value.enqueue.call_args.kwargs["report_date"]
        )

    def test_report_date_is_forwarded_to_the_task(self):
        with self.settings(TELEGRAM_BOT_API_SECRET=SECRET), patch(
            "django_rq.get_queue"
        ) as get_queue:
            get_queue.return_value.enqueue.return_value.id = "job-2"

            response = self.client.post(
                self.url,
                {"report_date": "2026-07-27"},
                format="json",
                HTTP_X_API_SECRET=SECRET,
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            get_queue.return_value.enqueue.call_args.kwargs["report_date"],
            "2026-07-27",
        )

    def test_wrong_secret_is_rejected_without_queueing(self):
        with self.settings(TELEGRAM_BOT_API_SECRET=SECRET), patch(
            "django_rq.get_queue"
        ) as get_queue:
            response = self.client.post(
                self.url, {}, format="json", HTTP_X_API_SECRET="wrong"
            )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        get_queue.assert_not_called()

    def test_missing_secret_header_is_rejected(self):
        with self.settings(TELEGRAM_BOT_API_SECRET=SECRET), patch(
            "django_rq.get_queue"
        ) as get_queue:
            response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        get_queue.assert_not_called()

    def test_unconfigured_secret_never_authenticates(self):
        # An empty configured secret must not make an empty header valid.
        with self.settings(TELEGRAM_BOT_API_SECRET=""), patch(
            "django_rq.get_queue"
        ) as get_queue:
            response = self.client.post(
                self.url, {}, format="json", HTTP_X_API_SECRET=""
            )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        get_queue.assert_not_called()

    def test_endpoint_requires_no_user_session(self):
        # Anonymous is expected — the caller is the bot, not a logged-in user.
        with self.settings(TELEGRAM_BOT_API_SECRET=SECRET), patch(
            "django_rq.get_queue"
        ) as get_queue:
            get_queue.return_value.enqueue.return_value.id = "job-3"

            response = self.client.post(
                self.url, {}, format="json", HTTP_X_API_SECRET=SECRET
            )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
