"""
Tests for vacancy analytics webhook functionality.

Tests cover:
- VacancyAnalyticsProtobufService encoding/decoding
- Vacancy payload building
- Data validation
- Round-trip encode/decode integrity
- Deactivation sync tracking (VacancyAnalyticsSync)
"""

from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone

from apps.general.models import VacancyAnalyticsSync
from apps.general.services.analytics.vacancy_protobuf_service import (
    VacancyAnalyticsProtobufService,
    WORKXPLORER_VACANCY_HEADER,
    VACANCY_PROTOBUF_VERSION,
)


def _make_sample_vacancy_payload(
        vacancy_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        company_id="c1d2e3f4-a5b6-7890-cdef-ab1234567890",
        is_active=True,
):
    """Build a representative vacancy analytics payload for testing."""
    return {
        "source": "workxplorer",
        "timestamp": "2026-02-10T12:00:00+05:00",
        "meta": {
            "env": "test",
            "company_id": company_id,
            "vacancy_id": vacancy_id,
        },
        "vacancy": {
            "id": vacancy_id,
            "title": "Senior Python Developer",
            "domain": "IT",
            "domain_id": "d1e2f3a4-b5c6-7890-1234-567890abcdef",
            "created_at": "2026-01-15T09:00:00+05:00",
            "updated_at": "2026-02-10T11:00:00+05:00",
            "created_by_email": "recruiter@example.com",
            "employment_type": "full_time",
            "employment_format": "remote",
            "is_active": is_active,
            "number_of_positions": 3,
            "salary_min": "2000",
            "salary_max": "5000",
            "salary_currency": "USD",
            "cards": {
                "time_to_hire": {
                    "hired_count": 2,
                    "total_days_to_hire": 45,
                    "hire_records": [
                        {
                            "application_id": "app-001",
                            "applied_at": "2026-01-20T10:00:00+05:00",
                            "hired_at": "2026-02-05T10:00:00+05:00",
                            "days_to_hire": 16,
                        },
                        {
                            "application_id": "app-002",
                            "applied_at": "2026-01-16T10:00:00+05:00",
                            "hired_at": "2026-02-09T10:00:00+05:00",
                            "days_to_hire": 24,
                        },
                    ],
                },
                "conversion": {
                    "total_applications": 50,
                    "total_hired": 2,
                },
                "views": {
                    "total_views": 320,
                    "unique_viewers": 210,
                },
                "applications": {
                    "count": 50,
                },
                "average_age": {
                    "applicants_with_age": 45,
                    "total_age_sum": 1125,
                },
                "response_funnel": {
                    "views_count": 320,
                    "applications_count": 50,
                    "invitations_count": 15,
                    "interviews_count": 8,
                    "offers_count": 3,
                },
                "top_skills": {
                    "total_candidates": 50,
                    "total_candidates_with_skills": 42,
                    "skills": [
                        {"skill_id": "s1", "skill_name": "Python", "candidates_count": 35},
                        {"skill_id": "s2", "skill_name": "Django", "candidates_count": 28},
                        {"skill_id": "s3", "skill_name": "PostgreSQL", "candidates_count": 20},
                    ],
                },
                "candidates_by_region": {
                    "total_candidates": 50,
                    "candidates_with_region": 48,
                    "average_age": 25.0,
                    "regions": [
                        {
                            "region_code": "Toshkent",
                            "region_name": "Toshkent shahri",
                            "candidates_count": 30,
                            "average_age": 24.5,
                            "edupartners": [
                                {"edupartner_name": "TUIT", "count": 12},
                                {"edupartner_name": "INHA", "count": 8},
                            ],
                        },
                        {
                            "region_code": "Samarqand",
                            "region_name": "Samarqand viloyati",
                            "candidates_count": 10,
                            "average_age": 26.0,
                            "edupartners": [
                                {"edupartner_name": "SamDU", "count": 5},
                            ],
                        },
                    ],
                },
            },
        },
        "analytics_timestamp": "2026-02-10T12:00:01+05:00",
    }


class VacancyAnalyticsProtobufEncodingTest(TestCase):
    """Tests for protobuf encoding of vacancy analytics data."""

    def test_encode_returns_bytes_with_correct_header(self):
        """Encoded data must start with the WKXP header."""
        payload = _make_sample_vacancy_payload()
        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)

        self.assertIsInstance(encoded, bytes)
        self.assertEqual(WORKXPLORER_VACANCY_HEADER, encoded[:4])

    def test_encode_returns_correct_version(self):
        """Encoded data must contain the correct version byte."""
        payload = _make_sample_vacancy_payload()
        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)

        self.assertEqual(encoded[4], VACANCY_PROTOBUF_VERSION)

    def test_encode_produces_compact_binary(self):
        """Protobuf encoding should be smaller than JSON."""
        import json

        payload = _make_sample_vacancy_payload()
        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)
        json_size = len(json.dumps(payload, default=str).encode("utf-8"))

        self.assertLess(len(encoded), json_size)

    def test_encode_empty_cards(self):
        """Encoding should handle vacancies with empty/minimal card data."""
        payload = _make_sample_vacancy_payload()
        payload["vacancy"]["cards"] = {}

        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)
        self.assertIsInstance(encoded, bytes)
        self.assertGreater(len(encoded), 9)


class VacancyAnalyticsProtobufDecodingTest(TestCase):
    """Tests for protobuf decoding of vacancy analytics data."""

    def test_round_trip_preserves_data(self):
        """Encode then decode should preserve all key data."""
        payload = _make_sample_vacancy_payload()
        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)
        decoded = VacancyAnalyticsProtobufService.decode_vacancy_data(encoded)

        self.assertEqual(decoded["source"], "workxplorer")
        self.assertEqual(decoded["meta"]["company_id"], payload["meta"]["company_id"])
        self.assertEqual(decoded["meta"]["vacancy_id"], payload["meta"]["vacancy_id"])

        vacancy = decoded["vacancy"]
        self.assertEqual(vacancy["id"], payload["vacancy"]["id"])
        self.assertEqual(vacancy["title"], "Senior Python Developer")
        self.assertEqual(vacancy["is_active"], True)
        self.assertEqual(vacancy["number_of_positions"], 3)

    def test_round_trip_preserves_cards(self):
        """Card metrics should survive encode/decode."""
        payload = _make_sample_vacancy_payload()
        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)
        decoded = VacancyAnalyticsProtobufService.decode_vacancy_data(encoded)

        cards = decoded["vacancy"]["cards"]

        self.assertEqual(cards["time_to_hire"]["hired_count"], 2)
        self.assertEqual(cards["time_to_hire"]["total_days_to_hire"], 45)
        self.assertEqual(len(cards["time_to_hire"]["hire_records"]), 2)

        self.assertEqual(cards["conversion"]["total_applications"], 50)
        self.assertEqual(cards["conversion"]["total_hired"], 2)

        self.assertEqual(cards["views"]["total_views"], 320)
        self.assertEqual(cards["applications"]["count"], 50)

        self.assertEqual(cards["response_funnel"]["views_count"], 320)
        self.assertEqual(cards["response_funnel"]["offers_count"], 3)

        self.assertEqual(len(cards["top_skills"]["skills"]), 3)
        self.assertEqual(cards["top_skills"]["skills"][0]["skill_name"], "Python")

        self.assertEqual(len(cards["candidates_by_region"]["regions"]), 2)
        self.assertEqual(
            cards["candidates_by_region"]["regions"][0]["region_code"], "Toshkent"
        )

    def test_round_trip_inactive_vacancy(self):
        """is_active=False should be preserved through encode/decode."""
        payload = _make_sample_vacancy_payload(is_active=False)
        encoded = VacancyAnalyticsProtobufService.encode_vacancy_data(payload)
        decoded = VacancyAnalyticsProtobufService.decode_vacancy_data(encoded)

        self.assertFalse(decoded["vacancy"]["is_active"])

    def test_decode_rejects_bad_header(self):
        """Decoding data with wrong header should raise ValueError."""
        bad_data = b"BAAD" + b"\x01" + b"\x00\x00\x00\x00"
        with self.assertRaises(ValueError):
            VacancyAnalyticsProtobufService.decode_vacancy_data(bad_data)

    def test_decode_rejects_short_data(self):
        """Decoding data shorter than 9 bytes should raise ValueError."""
        with self.assertRaises(ValueError):
            VacancyAnalyticsProtobufService.decode_vacancy_data(b"short")

    def test_decode_rejects_wrong_version(self):
        """Decoding data with unsupported version should raise ValueError."""
        bad_data = WORKXPLORER_VACANCY_HEADER + b"\x99" + b"\x00\x00\x00\x00"
        with self.assertRaises(ValueError):
            VacancyAnalyticsProtobufService.decode_vacancy_data(bad_data)


class VacancyAnalyticsValidationTest(TestCase):
    """Tests for vacancy analytics data validation."""

    def test_valid_payload_passes(self):
        """A well-formed payload should pass validation."""
        payload = _make_sample_vacancy_payload()
        self.assertTrue(
            VacancyAnalyticsProtobufService.validate_vacancy_data(payload)
        )

    def test_missing_source_fails(self):
        """Payload without 'source' should fail validation."""
        payload = _make_sample_vacancy_payload()
        del payload["source"]
        self.assertFalse(
            VacancyAnalyticsProtobufService.validate_vacancy_data(payload)
        )

    def test_missing_vacancy_fails(self):
        """Payload without 'vacancy' should fail validation."""
        payload = _make_sample_vacancy_payload()
        del payload["vacancy"]
        self.assertFalse(
            VacancyAnalyticsProtobufService.validate_vacancy_data(payload)
        )

    def test_missing_vacancy_id_fails(self):
        """Payload without vacancy.id should fail validation."""
        payload = _make_sample_vacancy_payload()
        payload["vacancy"]["id"] = ""
        self.assertFalse(
            VacancyAnalyticsProtobufService.validate_vacancy_data(payload)
        )

    def test_missing_meta_vacancy_id_fails(self):
        """Payload without meta.vacancy_id should fail validation."""
        payload = _make_sample_vacancy_payload()
        payload["meta"]["vacancy_id"] = ""
        self.assertFalse(
            VacancyAnalyticsProtobufService.validate_vacancy_data(payload)
        )


class CompanyAnalyticsNoVacanciesTest(TestCase):
    """
    Verify that company analytics payload no longer includes vacancy data.
    This tests the protobuf service encoding side.
    """

    def test_company_protobuf_encodes_without_vacancies(self):
        """Company protobuf message should not contain vacancy data."""
        from apps.general.services.analytics.protobuf_service import HRAnalyticsProtobufService
        from apps.general.services.analytics import hr_analytics_pb2

        # Test through the public encode/decode interface instead of private methods
        analytics_data = {
            "company": {
                "id": "test-company-id",
                "name": "Test Corp",
                "domain": "IT",
                "tin": "123456789",
                "is_active": True,
                "description": "A test company",
                "address": "Tashkent",
                "website": "https://test.com",
                "photo": None,
            },
            "vacancies": []
        }

        # Encode and decode through public interface
        binary_data = HRAnalyticsProtobufService.encode_analytics_data(analytics_data)
        decoded_data = HRAnalyticsProtobufService.decode_analytics_data(binary_data)

        # Verify company data is preserved
        company = decoded_data["company"]
        self.assertEqual(company["id"], "test-company-id")
        self.assertEqual(company["name"], "Test Corp")

        # Check protobuf schema: Company message should not have a 'vacancies' field
        # This verifies the protobuf definition itself
        company_fields = [f.name for f in hr_analytics_pb2.Company.DESCRIPTOR.fields]
        self.assertNotIn("vacancies", company_fields,
                         "Company protobuf should not contain vacancies field")


# ---------------------------------------------------------------------------
# Deactivation Sync tests
# ---------------------------------------------------------------------------


def _create_test_company_and_recruiter():
    """Create a minimal Company + Recruiter for test vacancies."""
    from apps.authentication.models import Company, Recruiter

    company = Company.objects.create(name="Sync Test Co", tin="111222333")
    recruiter = Recruiter.objects.create_user(
        email=f"recruiter_{company.id}@test.com",
        password="testpass123",
        is_recruiter=True,
    )
    return company, recruiter


class GetVacanciesForAnalyticsTest(TestCase):
    """Tests for _get_vacancies_for_analytics filtering logic."""

    @classmethod
    def setUpTestData(cls):
        from apps.vacancies.models import Vacancy

        cls.company, cls.recruiter = _create_test_company_and_recruiter()

        cls.active1 = Vacancy.objects.create(
            title="Active Vacancy 1",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=True,
        )
        cls.active2 = Vacancy.objects.create(
            title="Active Vacancy 2",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=True,
        )
        cls.inactive_unsynced = Vacancy.objects.create(
            title="Inactive Not-Yet-Synced",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=False,
        )
        cls.inactive_synced = Vacancy.objects.create(
            title="Inactive Already-Synced",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=False,
        )
        # Pre-mark one inactive vacancy as already synced
        VacancyAnalyticsSync.objects.create(
            vacancy_id=cls.inactive_synced.id,
            deactivation_synced_at=timezone.now(),
        )

    def test_active_vacancies_always_included(self):
        """Active vacancies should always appear in the result set."""
        from apps.general.tasks import _get_vacancies_for_analytics

        result = _get_vacancies_for_analytics(str(self.company.id))
        result_ids = {v.id for v in result}

        self.assertIn(self.active1.id, result_ids)
        self.assertIn(self.active2.id, result_ids)

    def test_inactive_unsynced_included(self):
        """Inactive vacancies whose deactivation was NOT synced must be included."""
        from apps.general.tasks import _get_vacancies_for_analytics

        result = _get_vacancies_for_analytics(str(self.company.id))
        result_ids = {v.id for v in result}

        self.assertIn(self.inactive_unsynced.id, result_ids)

    def test_inactive_synced_excluded(self):
        """Inactive vacancies whose deactivation WAS synced must be excluded."""
        from apps.general.tasks import _get_vacancies_for_analytics

        result = _get_vacancies_for_analytics(str(self.company.id))
        result_ids = {v.id for v in result}

        self.assertNotIn(self.inactive_synced.id, result_ids)

    def test_reactivated_vacancy_clears_sync(self):
        """
        If a vacancy was synced as deactivated but then reactivated,
        the sync record should be cleared.
        """
        from apps.vacancies.models import Vacancy
        from apps.general.tasks import _get_vacancies_for_analytics

        # Reactivate the previously-synced vacancy
        v = Vacancy.objects.get(id=self.inactive_synced.id)
        v.is_active = True
        v.save(update_fields=["is_active"])

        result = _get_vacancies_for_analytics(str(self.company.id))
        result_ids = {v.id for v in result}

        # Should now be included (active)
        self.assertIn(self.inactive_synced.id, result_ids)

        # Sync record should have been cleared
        sync = VacancyAnalyticsSync.objects.get(vacancy_id=self.inactive_synced.id)
        self.assertIsNone(sync.deactivation_synced_at)


class MarkDeactivationSyncedTest(TestCase):
    """Tests for _mark_deactivation_synced."""

    def test_creates_sync_record(self):
        """First deactivation sync should create a new record."""
        from apps.general.tasks import _mark_deactivation_synced

        vacancy_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        _mark_deactivation_synced(vacancy_id)

        sync = VacancyAnalyticsSync.objects.get(vacancy_id=vacancy_id)
        self.assertIsNotNone(sync.deactivation_synced_at)

    def test_updates_existing_record(self):
        """Calling again should update, not duplicate."""
        from apps.general.tasks import _mark_deactivation_synced

        vacancy_id = "aaaaaaaa-bbbb-cccc-dddd-ffffffffffff"
        VacancyAnalyticsSync.objects.create(
            vacancy_id=vacancy_id,
            deactivation_synced_at=None,
        )

        _mark_deactivation_synced(vacancy_id)

        self.assertEqual(
            VacancyAnalyticsSync.objects.filter(vacancy_id=vacancy_id).count(), 1
        )
        sync = VacancyAnalyticsSync.objects.get(vacancy_id=vacancy_id)
        self.assertIsNotNone(sync.deactivation_synced_at)


class SendSingleCompanyVacancyAnalyticsDeactivationTest(TestCase):
    """
    Integration tests for send_single_company_vacancy_analytics
    focusing on deactivation sync behaviour.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.vacancies.models import Vacancy

        cls.company, cls.recruiter = _create_test_company_and_recruiter()

        cls.active = Vacancy.objects.create(
            title="Active Job",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=True,
        )
        cls.inactive = Vacancy.objects.create(
            title="Closed Job",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=False,
        )

    @patch("apps.general.tasks._send_vacancy_to_service")
    @patch("apps.general.tasks._build_vacancy_payload")
    def test_inactive_vacancy_marked_after_successful_send(
            self, mock_build, mock_send,
    ):
        """
        After successfully sending an inactive vacancy, the sync record
        should be created with deactivation_synced_at set.
        """
        from apps.general.tasks import send_single_company_vacancy_analytics

        mock_build.return_value = _make_sample_vacancy_payload(
            vacancy_id=str(self.inactive.id),
            company_id=str(self.company.id),
            is_active=False,
        )
        mock_send.return_value = {"status": "ok", "status_code": 200}

        result = send_single_company_vacancy_analytics(str(self.company.id))

        self.assertIn(result["status"], ("success", "partial_success"))
        self.assertEqual(result["deactivation_synced"], 1)

        sync = VacancyAnalyticsSync.objects.get(vacancy_id=self.inactive.id)
        self.assertIsNotNone(sync.deactivation_synced_at)

    @patch("apps.general.tasks._send_vacancy_to_service")
    @patch("apps.general.tasks._build_vacancy_payload")
    def test_active_vacancy_not_marked(self, mock_build, mock_send):
        """Active vacancies should NOT produce a sync record."""
        from apps.general.tasks import send_single_company_vacancy_analytics

        mock_build.return_value = _make_sample_vacancy_payload(
            vacancy_id=str(self.active.id),
            company_id=str(self.company.id),
            is_active=True,
        )
        mock_send.return_value = {"status": "ok", "status_code": 200}

        send_single_company_vacancy_analytics(str(self.company.id))

        self.assertFalse(
            VacancyAnalyticsSync.objects.filter(
                vacancy_id=self.active.id,
                deactivation_synced_at__isnull=False,
            ).exists()
        )

    @patch("apps.general.tasks._send_vacancy_to_service")
    @patch("apps.general.tasks._build_vacancy_payload")
    def test_failed_send_does_not_mark_sync(self, mock_build, mock_send):
        """
        If the send fails, the vacancy must NOT be marked as synced
        so it is retried on the next run.
        """
        from apps.general.tasks import send_single_company_vacancy_analytics

        mock_build.return_value = _make_sample_vacancy_payload(
            vacancy_id=str(self.inactive.id),
            company_id=str(self.company.id),
            is_active=False,
        )
        mock_send.side_effect = Exception("Connection refused")

        send_single_company_vacancy_analytics(str(self.company.id))

        self.assertFalse(
            VacancyAnalyticsSync.objects.filter(
                vacancy_id=self.inactive.id,
                deactivation_synced_at__isnull=False,
            ).exists()
        )

    @patch("apps.general.tasks._send_vacancy_to_service")
    @patch("apps.general.tasks._build_vacancy_payload")
    def test_synced_inactive_excluded_on_second_run(
            self, mock_build, mock_send,
    ):
        """
        After a successful deactivation sync, the inactive vacancy
        should no longer appear in subsequent runs.
        """
        from apps.general.tasks import (
            send_single_company_vacancy_analytics,
            _get_vacancies_for_analytics,
        )

        # First run: sends both active + inactive
        mock_build.return_value = _make_sample_vacancy_payload(is_active=False)
        mock_send.return_value = {"status": "ok", "status_code": 200}

        send_single_company_vacancy_analytics(str(self.company.id))

        # Second run: inactive should be excluded
        result = _get_vacancies_for_analytics(str(self.company.id))
        result_ids = {v.id for v in result}

        self.assertIn(self.active.id, result_ids)
        self.assertNotIn(self.inactive.id, result_ids)
