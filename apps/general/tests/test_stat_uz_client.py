from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from apps.general.services import stat_uz_client

SAMPLE_SECTOR = {
    "id": 236,
    "name": "Аxborot vа аloqа",
    "name_uz": "Аxborot vа аloqа",
    "name_ru": "Информация и связь",
    "name_en": "Information and communication",
    "name_uzc": "Ахборот ва алоқа",
    "is_root": False,
    "map_code": None,
    "data": [
        {"2025-Q4": 15298086.3},
        {"2026-Q1": 16525372.8},
        {"2026-Q2": 17417383.4},
    ],
}


class FetchSectorSalaryTableTests(TestCase):
    @override_settings(STAT_UZ_API_BASE_URL="https://siat.stat.uz", STAT_UZ_SALARY_DATASET_ID="506")
    @patch("apps.general.services.stat_uz_client.requests.get")
    def test_requests_expected_url_and_headers(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [SAMPLE_SECTOR]
        mock_get.return_value = mock_response

        result = stat_uz_client.fetch_sector_salary_table()

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://siat.stat.uz/api/sdmx/506/table/")
        self.assertEqual(kwargs["headers"]["Accept"], "application/json")
        self.assertEqual(result, [SAMPLE_SECTOR])


class ParseSectorSalaryRowsTests(TestCase):
    def test_flattens_sector_periods_into_rows(self):
        rows = stat_uz_client.parse_sector_salary_rows([SAMPLE_SECTOR], dataset_id="506")

        self.assertEqual(len(rows), 3)
        row = next(r for r in rows if r["period_label"] == "2026-Q2")
        self.assertEqual(row["sector_code"], "236")
        self.assertEqual(row["sector_name"], "Information and communication")
        self.assertEqual(row["period_type"], "quarterly")
        self.assertEqual(row["avg_salary_uzs"], Decimal("17417383.40"))
        self.assertEqual(row["source_dataset_id"], "506")

    def test_skips_sector_without_id(self):
        sector = dict(SAMPLE_SECTOR)
        sector.pop("id")
        rows = stat_uz_client.parse_sector_salary_rows([sector])
        self.assertEqual(rows, [])

    def test_skips_unparseable_value(self):
        sector = dict(SAMPLE_SECTOR)
        sector["data"] = [{"2026-Q2": "n/a"}]
        rows = stat_uz_client.parse_sector_salary_rows([sector])
        self.assertEqual(rows, [])

    def test_empty_input(self):
        self.assertEqual(stat_uz_client.parse_sector_salary_rows([]), [])
        self.assertEqual(stat_uz_client.parse_sector_salary_rows(None), [])
