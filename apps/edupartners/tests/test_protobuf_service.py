from django.test import TestCase
from apps.edupartners.services.protobuf_service import EduPartnerAnalyticsProtobufService


class ProtobufServiceTestCase(TestCase):
    """Test case for protobuf analytics encoding/decoding."""

    def setUp(self):
        """Set up test data with 9 cards."""
        self.test_analytics_data = {
            "edupartner_id": "test-uuid-123",
            "edupartner_name": "Test University",
            "faculty_id": "faculty-uuid-456",
            "faculty_name": "Computer Science Faculty",
            "faculty_domain": "Technology",
            "cards": {
                "source_students": {
                    "value": 2480,
                    "label": "Из источника",
                },
                "registered": {
                    "value": 1760,
                    "label": "Зарегистрировано",
                },
                "active_30_days": {
                    "value": 1044,
                    "label": "Активные 30 дней",
                },
                "resume_uploaded": {
                    "value": 1020,
                    "label": "Резюме загружено",
                },
                "profile_filled": {
                    "value": 1124,
                    "label": "Профиль заполнен",
                },
                "assessment_passed": {
                    "value": 725,
                    "label": "Assessment пройден",
                },
                "graduate_salary": {
                    "value": 6200000,
                    "currency": "UZS",
                    "label": "Ср. зарплата выпускников",
                },
                "students_on_internships": {
                    "value": 84,
                    "label": "Кол-во студентов на стажировках",
                },
                "total_vacancies": {
                    "value": 312,
                    "label": "Всего вакансий",
                },
            },
            "popular_industries": {
                "7_days": [],
                "30_days": [],
                "12_months": []
            },
            "employed_graduates": {
                "total_graduates": 100,
                "employed_count": 85,
                "employment_rate_percentage": 85.0,
                "by_status": {"EMPLOYED": 85, "UNEMPLOYED": 15}
            },
            "hiring_funnel": {
                "resumes_created": 200,
                "interviewed": 120,
                "offered": 90,
                "hired": 50,
                "conversion_rates": {
                    "resume_to_interview": 60.0,
                    "interview_to_offer": 75.0,
                    "offer_to_hire": 55.6,
                    "overall_conversion": 25.0
                }
            },
            "top_companies_by_placements": [],
            "timestamp": "2023-12-18T12:14:14.407Z"
        }

    def test_validate_analytics_data(self):
        """Test data validation functionality."""
        self.assertTrue(
            EduPartnerAnalyticsProtobufService.validate_analytics_data(self.test_analytics_data)
        )

        invalid_data = self.test_analytics_data.copy()
        del invalid_data['edupartner_id']

        self.assertFalse(
            EduPartnerAnalyticsProtobufService.validate_analytics_data(invalid_data)
        )

    def test_encode_analytics_data(self):
        """Test protobuf encoding."""
        binary_data = EduPartnerAnalyticsProtobufService.encode_analytics_data(
            self.test_analytics_data
        )

        self.assertIsInstance(binary_data, bytes)
        self.assertTrue(binary_data.startswith(b'WKXP'))
        self.assertGreater(len(binary_data), 0)

    def test_decode_analytics_data(self):
        """Test protobuf decoding."""
        binary_data = EduPartnerAnalyticsProtobufService.encode_analytics_data(
            self.test_analytics_data
        )

        decoded_data = EduPartnerAnalyticsProtobufService.decode_analytics_data(binary_data)

        self.assertEqual(decoded_data, self.test_analytics_data)

    def test_encoding_efficiency(self):
        """Test encoding provides size reduction."""
        encoding_info = EduPartnerAnalyticsProtobufService.get_encoding_info(
            self.test_analytics_data
        )

        self.assertIn('json_size_bytes', encoding_info)
        self.assertIn('protobuf_size_bytes', encoding_info)
        self.assertIn('compression_ratio_percent', encoding_info)

        self.assertLessEqual(
            encoding_info['protobuf_size_bytes'],
            encoding_info['json_size_bytes']
        )

    def test_round_trip_data_integrity(self):
        """Test that data survives encoding/decoding round trip."""
        binary_data = EduPartnerAnalyticsProtobufService.encode_analytics_data(
            self.test_analytics_data
        )

        decoded_data = EduPartnerAnalyticsProtobufService.decode_analytics_data(binary_data)

        self.assertEqual(decoded_data['edupartner_name'], 'Test University')
        self.assertEqual(decoded_data['faculty_name'], 'Computer Science Faculty')
        self.assertEqual(decoded_data['cards']['source_students']['value'], 2480)
        self.assertEqual(decoded_data['cards']['registered']['value'], 1760)
        self.assertEqual(decoded_data['cards']['active_30_days']['value'], 1044)
        self.assertEqual(decoded_data['cards']['resume_uploaded']['value'], 1020)
        self.assertEqual(decoded_data['cards']['profile_filled']['value'], 1124)
        self.assertEqual(decoded_data['cards']['assessment_passed']['value'], 725)
        self.assertEqual(decoded_data['cards']['graduate_salary']['value'], 6200000)
        self.assertEqual(decoded_data['cards']['graduate_salary']['currency'], 'UZS')
        self.assertEqual(decoded_data['cards']['students_on_internships']['value'], 84)
        self.assertEqual(decoded_data['cards']['total_vacancies']['value'], 312)
        self.assertEqual(decoded_data['employed_graduates']['total_graduates'], 100)

        self.assertEqual(decoded_data, self.test_analytics_data)

    def test_invalid_binary_data(self):
        """Test handling of invalid binary data."""
        with self.assertRaises(ValueError):
            EduPartnerAnalyticsProtobufService.decode_analytics_data(b'INVALID_DATA')

        with self.assertRaises(ValueError):
            EduPartnerAnalyticsProtobufService.decode_analytics_data(b'SHORT')
