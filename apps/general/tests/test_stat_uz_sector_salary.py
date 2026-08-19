from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.general.services import stat_uz_sector_salary

SAMPLE_SECTOR = {
    "id": 236,
    "name_en": "Information and communication",
    "data": [
        {"2025-Q4": 15298086.3},
        {"2026-Q1": 16525372.8},
        {"2026-Q2": 17417383.4},
    ],
}


class SyncStatUzSectorSalariesTests(TestCase):
    @patch("apps.general.services.stat_uz_sector_salary.fetch_sector_salary_table")
    def test_sync_upserts_rows(self, mock_fetch):
        from apps.general.models import StatUzSectorSalary

        mock_fetch.return_value = [SAMPLE_SECTOR]

        synced = stat_uz_sector_salary.sync_stat_uz_sector_salaries()

        self.assertEqual(synced, 3)
        self.assertEqual(StatUzSectorSalary.objects.count(), 3)
        row = StatUzSectorSalary.objects.get(sector_code="236", period_label="2026-Q2")
        self.assertEqual(row.avg_salary_uzs, Decimal("17417383.40"))
        self.assertEqual(row.sector_name, "Information and communication")

    @patch("apps.general.services.stat_uz_sector_salary.fetch_sector_salary_table")
    def test_sync_is_idempotent_and_updates_values(self, mock_fetch):
        from apps.general.models import StatUzSectorSalary

        mock_fetch.return_value = [SAMPLE_SECTOR]
        stat_uz_sector_salary.sync_stat_uz_sector_salaries()

        updated_sector = dict(SAMPLE_SECTOR)
        updated_sector["data"] = [{"2026-Q2": 18000000.0}]
        mock_fetch.return_value = [updated_sector]
        stat_uz_sector_salary.sync_stat_uz_sector_salaries()

        self.assertEqual(StatUzSectorSalary.objects.count(), 3)
        row = StatUzSectorSalary.objects.get(sector_code="236", period_label="2026-Q2")
        self.assertEqual(row.avg_salary_uzs, Decimal("18000000.00"))


class GetLatestSectorSalaryTests(TestCase):
    def test_returns_most_recent_period(self):
        from apps.general.models import StatUzSectorSalary

        StatUzSectorSalary.objects.create(
            sector_code="236",
            sector_name="Information and communication",
            period_type="quarterly",
            period_label="2025-Q4",
            avg_salary_uzs=Decimal("15298086.30"),
            source_dataset_id="506",
        )
        StatUzSectorSalary.objects.create(
            sector_code="236",
            sector_name="Information and communication",
            period_type="quarterly",
            period_label="2026-Q2",
            avg_salary_uzs=Decimal("17417383.40"),
            source_dataset_id="506",
        )
        StatUzSectorSalary.objects.create(
            sector_code="236",
            sector_name="Information and communication",
            period_type="quarterly",
            period_label="2026-Q1",
            avg_salary_uzs=Decimal("16525372.80"),
            source_dataset_id="506",
        )

        latest = stat_uz_sector_salary.get_latest_sector_salary("236")
        self.assertEqual(latest["avg_salary_uzs"], Decimal("17417383.40"))
        self.assertEqual(latest["period_label"], "2026-Q2")

    def test_returns_none_when_no_data(self):
        self.assertIsNone(stat_uz_sector_salary.get_latest_sector_salary("999"))

    def test_returns_none_for_falsy_sector_code(self):
        self.assertIsNone(stat_uz_sector_salary.get_latest_sector_salary(None))
        self.assertIsNone(stat_uz_sector_salary.get_latest_sector_salary(""))
