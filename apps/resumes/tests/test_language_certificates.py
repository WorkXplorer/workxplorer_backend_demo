"""
Tests for ResumeLanguageCertificate model, serializer validation,
and integration with resume create/update endpoints.
"""
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.db.utils import IntegrityError
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.languages.models import Language
from apps.resumes.models import Resume, ResumeLanguageCertificate
from apps.resumes.models.choices import LanguageProficiencyLevel
from apps.authentication.models import Candidate


def _create_test_file(name="cert.jpg", size=1024, content_type="image/jpeg"):
    """Helper to create a test uploaded file."""
    content = b"\x00" * size
    return SimpleUploadedFile(name, content, content_type=content_type)


class ResumeLanguageCertificateModelTests(TestCase):
    """Test suite for ResumeLanguageCertificate model."""

    @classmethod
    def setUpTestData(cls):
        cls.candidate = Candidate.objects.create_user(
            email="langcert@test.com", password="testpass123"
        )
        cls.resume = Resume.objects.create(
            candidate=cls.candidate,
            title="My Resume",
            description="Developer Resume",
        )
        cls.english = Language.objects.create(name="English", code="en")
        cls.russian = Language.objects.create(name="Russian", code="ru")

    def test_create_language_certificate(self):
        lc = ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.english,
            level=LanguageProficiencyLevel.C1,
        )
        self.assertEqual(lc.language, self.english)
        self.assertEqual(lc.level, "C1")
        self.assertEqual(lc.resume, self.resume)

    def test_str_representation(self):
        lc = ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.english,
            level=LanguageProficiencyLevel.B2,
        )
        self.assertIn("English", str(lc))
        self.assertIn("B2", str(lc))

    def test_unique_resume_language_constraint(self):
        """Cannot have two certificates for the same language on one resume."""
        ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.english,
            level=LanguageProficiencyLevel.C1,
        )
        with self.assertRaises(IntegrityError):
            ResumeLanguageCertificate.objects.create(
                resume=self.resume,
                language=self.english,
                level=LanguageProficiencyLevel.B2,
            )

    def test_different_languages_allowed(self):
        """Can have certificates for different languages on one resume."""
        ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.english,
            level=LanguageProficiencyLevel.C1,
        )
        ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.russian,
            level=LanguageProficiencyLevel.B1,
        )
        self.assertEqual(self.resume.language_certificates.count(), 2)

    def test_create_with_file(self):
        test_file = _create_test_file("english_cert.jpg")
        lc = ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.english,
            level=LanguageProficiencyLevel.C2,
            file=test_file,
        )
        self.assertTrue(lc.file)

    def test_cascade_delete_with_resume(self):
        ResumeLanguageCertificate.objects.create(
            resume=self.resume,
            language=self.english,
            level=LanguageProficiencyLevel.C1,
        )
        # Create a new resume for testing cascade delete
        new_resume = Resume.objects.create(
            candidate=self.candidate,
            title="Temp Resume",
            description="Temp",
        )
        ResumeLanguageCertificate.objects.create(
            resume=new_resume,
            language=self.english,
            level=LanguageProficiencyLevel.A1,
        )
        new_resume.delete()
        self.assertFalse(
            ResumeLanguageCertificate.objects.filter(resume_id=new_resume.id).exists()
        )

    def test_all_cefr_levels_valid(self):
        """All CEFR levels should be valid choices."""
        valid = [c[0] for c in LanguageProficiencyLevel.choices]
        self.assertEqual(valid, ["A1", "A2", "B1", "B2", "C1", "C2"])


class ResumeLanguageCertificateSerializerTests(TestCase):
    """Test validation logic in ResumeSerializer for language_certificates_data."""

    @classmethod
    def setUpTestData(cls):
        cls.candidate = Candidate.objects.create_user(
            email="serializer_lang@test.com", password="testpass123"
        )
        cls.english = Language.objects.create(name="English", code="en")
        cls.russian = Language.objects.create(name="Russian", code="ru")
        cls.french = Language.objects.create(name="French", code="fr")

    def _get_serializer(self, data, instance=None):
        from apps.resumes.serializers.resume import ResumeSerializer
        if instance:
            return ResumeSerializer(instance, data=data, partial=True)
        return ResumeSerializer(data=data)

    def test_valid_language_certificates(self):
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id, "level": "C1"},
                {"language_id": self.russian.id, "level": "B2"},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_duplicate_language_in_request_rejected(self):
        """Two entries with the same language_id should be rejected."""
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id, "level": "C1"},
                {"language_id": self.english.id, "level": "B2"},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_nonexistent_language_rejected(self):
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": 99999, "level": "C1"},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_invalid_level_rejected(self):
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id, "level": "Z9"},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_missing_language_id_rejected(self):
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"level": "C1"},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_missing_level_rejected(self):
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_empty_list_valid(self):
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [],
        }
        serializer = self._get_serializer(data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_file_exceeding_size_rejected(self):
        """Files larger than 5MB should be rejected."""
        big_file = _create_test_file("big.jpg", size=6 * 1024 * 1024)
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id, "level": "C1", "file": big_file},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_invalid_file_extension_rejected(self):
        """Files with disallowed extensions should be rejected."""
        bad_file = _create_test_file("doc.exe", size=1024)
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id, "level": "C1", "file": bad_file},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("language_certificates_data", serializer.errors)

    def test_valid_file_accepted(self):
        valid_file = _create_test_file("cert.png", size=1024)
        data = {
            "description": "Test resume",
            "position": "Developer",
            "language_certificates_data": [
                {"language_id": self.english.id, "level": "C1", "file": valid_file},
            ],
        }
        serializer = self._get_serializer(data)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class ResumeLanguageCertificateAPITests(APITestCase):
    """Integration tests for language certificates via resume create/update API."""

    def setUp(self):
        self.candidate = Candidate.objects.create_user(
            email="api_lang@test.com", password="testpass123"
        )
        self.english = Language.objects.create(name="English", code="en")
        self.russian = Language.objects.create(name="Russian", code="ru")
        self.french = Language.objects.create(name="French", code="fr")

        self.client = APIClient()
        self.client.force_authenticate(user=self.candidate)

        self.create_url = "/api/v1/resumes/create/"

    def _create_resume_with_lang_certs(self, lang_certs_data):
        """Helper to create a resume with language certificates via API."""
        payload = {
            "description": "Test resume with languages",
            "position": "Developer",
            "language_certificates_data": json.dumps(lang_certs_data),
        }
        return self.client.post(self.create_url, payload, format="multipart")

    def test_create_resume_with_language_certificates(self):
        response = self._create_resume_with_lang_certs([
            {"language_id": self.english.id, "level": "C1"},
            {"language_id": self.russian.id, "level": "B2"},
        ])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data.get("data", response.data)
        lang_certs = data.get("language_certificates", [])
        self.assertEqual(len(lang_certs), 2)

    def test_create_resume_with_file_upload(self):
        """Test creating resume with language certificate file."""
        lang_data = json.dumps([
            {"language_id": self.english.id, "level": "C1"},
        ])
        test_file = _create_test_file("english_cert.jpg")
        payload = {
            "description": "Resume with cert file",
            "position": "Designer",
            "language_certificates_data": lang_data,
            "language_certificate_file_0": test_file,
        }
        response = self.client.post(self.create_url, payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data.get("data", response.data)
        lang_certs = data.get("language_certificates", [])
        self.assertEqual(len(lang_certs), 1)
        self.assertIsNotNone(lang_certs[0].get("file_url"))

    def test_create_resume_duplicate_language_rejected(self):
        """Duplicate language_id should fail validation."""
        response = self._create_resume_with_lang_certs([
            {"language_id": self.english.id, "level": "C1"},
            {"language_id": self.english.id, "level": "B2"},
        ])
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST])

    def test_update_resume_language_certificates(self):
        """Test updating language certificates on an existing resume."""
        # First create a resume with one language
        create_resp = self._create_resume_with_lang_certs([
            {"language_id": self.english.id, "level": "C1"},
        ])
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        resume_data = create_resp.data.get("data", create_resp.data)
        resume_id = resume_data["id"]

        # Update: replace English C1 with Russian B1
        update_url = f"/api/v1/resumes/{resume_id}/update/"
        update_payload = {
            "language_certificates_data": json.dumps([
                {"language_id": self.russian.id, "level": "B1"},
            ]),
        }
        update_resp = self.client.patch(update_url, update_payload, format="multipart")
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)
        updated_data = update_resp.data.get("data", update_resp.data)
        lang_certs = updated_data.get("language_certificates", [])
        self.assertEqual(len(lang_certs), 1)
        self.assertEqual(lang_certs[0]["language_name"], "Russian")

    def test_update_resume_add_language_certificate(self):
        """Test adding a new language certificate during update."""
        # Create resume with English
        create_resp = self._create_resume_with_lang_certs([
            {"language_id": self.english.id, "level": "C1"},
        ])
        resume_data = create_resp.data.get("data", create_resp.data)
        resume_id = resume_data["id"]
        existing_lc_id = resume_data["language_certificates"][0]["id"]

        # Update: keep English and add French
        update_url = f"/api/v1/resumes/{resume_id}/update/"
        update_payload = {
            "language_certificates_data": json.dumps([
                {"id": existing_lc_id, "language_id": self.english.id, "level": "C1"},
                {"language_id": self.french.id, "level": "A2"},
            ]),
        }
        update_resp = self.client.patch(update_url, update_payload, format="multipart")
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)
        updated_data = update_resp.data.get("data", update_resp.data)
        lang_certs = updated_data.get("language_certificates", [])
        self.assertEqual(len(lang_certs), 2)

    def test_update_resume_remove_all_language_certificates(self):
        """Sending empty list should remove all language certificates."""
        create_resp = self._create_resume_with_lang_certs([
            {"language_id": self.english.id, "level": "C1"},
        ])
        resume_data = create_resp.data.get("data", create_resp.data)
        resume_id = resume_data["id"]

        update_url = f"/api/v1/resumes/{resume_id}/update/"
        update_payload = {
            "language_certificates_data": json.dumps([]),
        }
        update_resp = self.client.patch(update_url, update_payload, format="multipart")
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)
        updated_data = update_resp.data.get("data", update_resp.data)
        lang_certs = updated_data.get("language_certificates", [])
        self.assertEqual(len(lang_certs), 0)

    def test_response_includes_language_certificates(self):
        """Verify response structure for language certificates."""
        create_resp = self._create_resume_with_lang_certs([
            {"language_id": self.english.id, "level": "C1"},
        ])
        resume_data = create_resp.data.get("data", create_resp.data)
        lc = resume_data["language_certificates"][0]
        self.assertIn("id", lc)
        self.assertIn("language_id", lc)
        self.assertIn("language_name", lc)
        self.assertIn("language_code", lc)
        self.assertIn("level", lc)
        self.assertIn("file_url", lc)
        self.assertEqual(lc["level"], "C1")
        self.assertEqual(lc["language_name"], "English")
        self.assertEqual(lc["language_code"], "en")
