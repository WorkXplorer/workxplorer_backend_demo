from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.applications.models import DailyReportSnapshot
from apps.applications.tasks import send_daily_application_report_task


def payload_for(day: str, applications: int = 5) -> dict:
    return {
        "report_date": day,
        "totals": {"day": applications, "all_time": 100},
        "churn": {"window_days": 30},
    }


class DailyReportSnapshotTests(TestCase):
    def test_store_saves_the_payload_under_its_report_date(self):
        snapshot = DailyReportSnapshot.store(payload_for("2026-08-12"))

        self.assertEqual(snapshot.report_date, date(2026, 8, 12))
        self.assertEqual(snapshot.payload["totals"]["day"], 5)

    def test_re_running_a_day_replaces_it_rather_than_colliding(self):
        """Re-sending a missed day is routine; the newer payload should win."""
        DailyReportSnapshot.store(payload_for("2026-08-12", applications=5))
        DailyReportSnapshot.store(payload_for("2026-08-12", applications=9))

        self.assertEqual(DailyReportSnapshot.objects.count(), 1)
        self.assertEqual(
            DailyReportSnapshot.objects.get().payload["totals"]["day"], 9
        )

    def test_a_payload_without_a_date_is_not_stored(self):
        """A snapshot that cannot be placed on the timeline is worse than none."""
        self.assertIsNone(DailyReportSnapshot.store({"totals": {"day": 1}}))
        self.assertEqual(DailyReportSnapshot.objects.count(), 0)


class SnapshotOnDeliveryTests(TestCase):
    """The snapshot and the Telegram push must not be able to sink each other."""

    def setUp(self):
        self.payload = payload_for("2026-08-12")

    def test_the_payload_is_stored_when_the_report_is_sent(self):
        with patch(
            "apps.applications.services.daily_report.build_daily_application_report",
            return_value=self.payload,
        ), patch(
            "apps.applications.services.daily_report.send_daily_application_report",
            return_value=True,
        ):
            result = send_daily_application_report_task()

        self.assertTrue(result["stored"])
        self.assertTrue(result["delivered"])
        self.assertEqual(DailyReportSnapshot.objects.count(), 1)

    def test_the_payload_is_stored_even_when_telegram_delivery_fails(self):
        """Point-in-time numbers are unrecoverable, so they outrank delivery."""
        with patch(
            "apps.applications.services.daily_report.build_daily_application_report",
            return_value=self.payload,
        ), patch(
            "apps.applications.services.daily_report.send_daily_application_report",
            return_value=False,
        ):
            result = send_daily_application_report_task()

        self.assertTrue(result["stored"])
        self.assertFalse(result["delivered"])
        self.assertEqual(DailyReportSnapshot.objects.count(), 1)

    def test_a_storage_failure_does_not_stop_the_report_going_out(self):
        with patch(
            "apps.applications.services.daily_report.build_daily_application_report",
            return_value=self.payload,
        ), patch(
            "apps.applications.services.daily_report.send_daily_application_report",
            return_value=True,
        ), patch(
            "apps.applications.models.DailyReportSnapshot.store",
            side_effect=RuntimeError("database is down"),
        ):
            result = send_daily_application_report_task()

        self.assertFalse(result["stored"])
        self.assertTrue(result["delivered"])
