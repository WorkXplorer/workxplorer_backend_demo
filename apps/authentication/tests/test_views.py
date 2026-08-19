from unittest.mock import patch
from io import BytesIO

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.profiles.models import RecruiterProfile
from apps.resumes.models import Resume

User = get_user_model()


class GeneralUserRegisterViewTests(APITestCase):
    """
    Test suite for the General User Registration API endpoint.

    This endpoint allows only admin users (superusers) to register
    general users. It validates access permissions, required fields,
    and handles duplicate registrations.
    """

    @classmethod
    def setUpTestData(cls):
        """
        Set up test data:
        - Create an admin user (superuser) for authentication.
        - Prepare the registration URL.
        """
        cls.admin = User.objects.create_superuser(
            email="admin@example.com", password="adminpass123"
        )
        cls.url = reverse("register-general")

    def test_requires_admin_permission(self):
        """
        Ensure that only admin users can access this endpoint.

        Expected behavior:
        - Normal (non-admin) user: 403 Forbidden
        """
        normal_user = User.objects.create_user(
            email="normal@example.com", password="userpass123"
        )
        self.client.force_authenticate(user=normal_user)

        payload = {
            "email": "newuser@example.com",
            "password": "newpass123",
            "is_staff": False,
            "is_superuser": False,
        }
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_registration_by_admin(self):
        """
        Ensure that admin can successfully register a general user.

        Expected behavior:
        - Admin creates a user → returns 201 Created
        - User is stored in the database
        """
        self.client.force_authenticate(user=self.admin)
        payload = {
            "email": "newuser@example.com",
            "password": "strongpass123",
            "is_staff": False,
            "is_superuser": False,
        }
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify user exists in DB
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())

    def test_missing_required_fields(self):
        """
        Ensure that missing required fields return a 400 error.

        Expected behavior:
        - Missing password → 400 Bad Request
        - Missing email → 400 Bad Request
        """
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url, {"email": "incomplete@example.com"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_email_fails(self):
        """
        Ensure that duplicate email registration fails.

        Expected behavior:
        - Attempt to register with an existing email → 400 Bad Request
        """
        User.objects.create_user(email="dup@example.com", password="testpass123")
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url, {"email": "dup@example.com", "password": "anotherpass123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CandidateRegisterViewTests(APITestCase):
    """
    Test suite for the Candidate Registration API endpoint.

    This endpoint should:
    - Allow new candidates to register with a unique email and consent.
    - Return proper validation errors for missing fields or duplicate emails.
    """

    def setUp(self):
        """
        Set up the endpoint URL for candidate registration.
        """
        self.url = reverse("register-candidate")

    def test_successful_registration(self):
        """
        Ensure a candidate can successfully register with valid data.

        Expected behavior:
        - 201 Created response
        - Response contains candidate email in APIResponse envelope
        - Candidate is saved in DB with correct flags and no usable password yet
        """
        payload = {
            "email": "newcandidate@example.com",
            "agreed_to_all_consents": True,
        }
        with patch(
            "apps.authentication.serializers.candidate.ConsentService.validate_entity_type",
            return_value=(True, None, None),
        ), patch(
            "apps.authentication.serializers.candidate.ConsentService.create_consents_for_entity",
            return_value=None,
        ):
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["email"], payload["email"])

        # Verify candidate in DB
        candidate = Candidate.objects.get(email=payload["email"])
        self.assertTrue(candidate.is_candidate)
        self.assertFalse(candidate.has_usable_password())

    def test_missing_email(self):
        """
        Ensure registration fails if the email field is missing.

        Expected behavior:
        - 400 Bad Request
        - Response contains "Input validation failed"
        - error=True in response
        """
        payload = {"agreed_to_all_consents": True}
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("Input validation failed", response.data["error"]["message"])
        self.assertIn("email", response.data["error"]["field_errors"])

    def test_missing_consent(self):
        """
        Ensure registration fails if consent field is missing.

        Expected behavior:
        - 400 Bad Request
        - Response contains "Input validation failed"
        - Validation error includes agreed_to_all_consents field
        """
        payload = {"email": "test@example.com"}
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("Input validation failed", response.data["error"]["message"])
        self.assertIn("agreed_to_all_consents", response.data["error"]["field_errors"])

    def test_duplicate_email(self):
        """
        Ensure registration fails for existing user with usable password.
        """
        Candidate.objects.create_user(
            email="existing@example.com",
            password="StrongPassword123!",
            is_candidate=True,
        )

        payload = {
            "email": "existing@example.com",
            "agreed_to_all_consents": True,
        }

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("Input validation failed", response.data["error"]["message"])
        self.assertIn("email", response.data["error"]["field_errors"])


class CandidateStatusAPIViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("candidate-status")
        self.candidate = Candidate.objects.create_user(
            email="candidate-status@example.com",
            password="pass123",
            is_candidate=True,
            onboarding_progress={"create_profile": "2026-05-13T09:00:00+00:00"},
        )
        self.client.force_authenticate(user=self.candidate)

    def test_counts_ai_generated_resume_as_created_resume_step(self):
        Resume.objects.create(
            candidate=self.candidate,
            title="AI Resume",
            description="Generated from AI",
            created_by_type=Resume.CreatedByType.AI_GENERATED,
            is_reviewed=False,
        )

        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ru")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        resume_step = next(
            step
            for step in response.data["data"]["steps"]
            if step["code"] == "create_resume"
        )
        self.assertTrue(resume_step["completed"])
        self.assertEqual(response.data["data"]["status"], "create_resume")
        self.assertEqual(response.data["data"]["current_step"], "vacancy_apply")

        self.candidate.refresh_from_db()
        self.assertIn("create_profile", self.candidate.onboarding_progress)
        self.assertIn("create_resume", self.candidate.onboarding_progress)


class RecruiterRegisterViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("register-recruiter")
        self.company = Company.objects.create(
            name="Test Company",
            is_active=True,
        )
        self.valid_payload = {
            "email": "recruiter@example.com",
            "company": str(self.company.id),
            "full_name": "John Doe",
            "agreed_to_all_consents": True,
        }

    def test_successful_registration(self):
        with patch(
            "apps.authentication.serializers.recruiter.ConsentService.validate_entity_type",
            return_value=(True, None, None),
        ), patch(
            "apps.authentication.serializers.recruiter.ConsentService.create_consents_for_entity",
            return_value=None,
        ):
            response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("email", response.data["data"])
        # Verify that RecruiterProfile was created with the correct full_name
        recruiter = Recruiter.objects.get(email=self.valid_payload["email"])
        profile = RecruiterProfile.objects.get(recruiter=recruiter)
        self.assertEqual(profile.full_name, "John Doe")

    def test_duplicate_email(self):
        Recruiter.objects.create_user(
            email=self.valid_payload["email"],
            company_id=self.company.id,
        )
        with patch(
            "apps.authentication.serializers.recruiter.ConsentService.validate_entity_type",
            return_value=(True, None, None),
        ), patch(
            "apps.authentication.serializers.recruiter.ConsentService.create_consents_for_entity",
            return_value=None,
        ):
            response = self.client.post(self.url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["error"]["field_errors"])

    def test_missing_full_name(self):
        """Test that registration fails when full_name is missing"""
        invalid_payload = {
            "email": "test@example.com",
            "company": str(self.company.id),
            "agreed_to_all_consents": True,
        }
        with patch(
            "apps.authentication.serializers.recruiter.ConsentService.validate_entity_type",
            return_value=(True, None, None),
        ), patch(
            "apps.authentication.serializers.recruiter.ConsentService.create_consents_for_entity",
            return_value=None,
        ):
            response = self.client.post(self.url, invalid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("full_name", response.data["error"]["field_errors"])


class AdminRecruiterRegistrationViewTests(APITestCase):
    """
    Test suite for the RegisterRecruiterAPIView endpoint.
    This endpoint allows admin recruiters to register new recruiters with profiles.
    """

    @classmethod
    def setUpTestData(cls):
        """
        Set up test data:
        - Create a company
        - Create an admin recruiter with admin-level profile
        - Create a regular recruiter for permission testing
        """
        cls.company = Company.objects.create(
            name="Admin Registration Test Company",
            tin="123456789",
            is_active=True,
        )

        # Create admin recruiter
        cls.admin_recruiter = Recruiter.objects.create_user(
            email="admin_recruiter@example.com",
            password="adminpass123",
            is_recruiter=True,
            company=cls.company,
        )
        # Create admin-level profile
        RecruiterProfile.objects.create(
            recruiter=cls.admin_recruiter,
            full_name="Admin Recruiter",
            level=RecruiterProfile.Level.ADMIN,
        )

        # Create regular recruiter for permission testing
        cls.regular_recruiter = Recruiter.objects.create_user(
            email="regular_recruiter@example.com",
            password="regularpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.regular_recruiter,
            full_name="Regular Recruiter",
            level=RecruiterProfile.Level.RECRUITER,
        )

        cls.create_url = reverse("register-recruiter-admin")

    def test_admin_can_register_recruiter(self):
        """
        Ensure admin recruiters can register new recruiters.
        """
        self.client.force_authenticate(user=self.admin_recruiter)

        payload = {
            "email": "new_recruiter@example.com",
            "password": "securepass123",
            "full_name": "New Recruiter",
            "phone_number": "+998901234567",
            "level": "Recruiter",
        }

        response = self.client.post(self.create_url, payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify recruiter was created
        self.assertTrue(Recruiter.objects.filter(email="new_recruiter@example.com").exists())

        # Verify profile was created with correct data
        recruiter = Recruiter.objects.get(email="new_recruiter@example.com")
        profile = RecruiterProfile.objects.get(recruiter=recruiter)
        self.assertEqual(profile.full_name, "New Recruiter")
        self.assertEqual(profile.phone, "+998901234567")
        self.assertEqual(profile.level, RecruiterProfile.Level.RECRUITER)

    def test_regular_recruiter_cannot_register(self):
        """
        Ensure non-admin recruiters cannot access this endpoint.
        """
        self.client.force_authenticate(user=self.regular_recruiter)

        payload = {
            "email": "another_recruiter@example.com",
            "password": "securepass123",
            "full_name": "Another Recruiter",
        }

        response = self.client.post(self.create_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_fails(self):
        """
        Ensure unauthenticated users cannot access this endpoint.
        """
        payload = {
            "email": "unauthenticated@example.com",
            "password": "securepass123",
            "full_name": "Unauthenticated Recruiter",
        }

        response = self.client.post(self.create_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_duplicate_email_fails(self):
        """
        Ensure registration with existing email fails.
        """
        self.client.force_authenticate(user=self.admin_recruiter)

        payload = {
            "email": "regular_recruiter@example.com",  # Already exists
            "password": "securepass123",
            "full_name": "Duplicate Email Recruiter",
        }

        response = self.client.post(self.create_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data.get("error"))

    def test_missing_required_fields(self):
        """
        Ensure registration fails without required fields.
        """
        self.client.force_authenticate(user=self.admin_recruiter)

        # Missing password
        payload = {
            "email": "incomplete@example.com",
            "full_name": "Incomplete Recruiter",
        }

        response = self.client.post(self.create_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error"].get("field_errors", {}))

    def test_password_is_hashed_using_django_hasher(self):
        """
        Ensure password is hashed using Django's check_password.
        """
        self.client.force_authenticate(user=self.admin_recruiter)

        password = "testpassword123"

        payload = {
            "email": "password_test@example.com",
            "password": password,
            "full_name": "Password Test Recruiter",
        }

        response = self.client.post(self.create_url, payload, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify password is hashed correctly using Django's check_password
        recruiter = Recruiter.objects.get(email="password_test@example.com")
        self.assertTrue(recruiter.has_usable_password())
        self.assertTrue(recruiter.check_password(password))
        # Ensure it is NOT plain text
        self.assertNotEqual(recruiter.password, password)


class CompanyProfileCreateViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Company Profile Create Test",
            tin="987654321",
        )
        cls.admin_recruiter = Recruiter.objects.create_user(
            email="company_profile_admin@example.com",
            password="StrongPass123!",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.admin_recruiter,
            full_name="Company Profile Admin",
            level=RecruiterProfile.Level.ADMIN,
        )
        cls.url = reverse("company-profile-create")

    def setUp(self):
        self.client.force_authenticate(user=self.admin_recruiter)

    @staticmethod
    def _make_valid_jpeg(name="logo.jpg"):
        from PIL import Image

        image = Image.new("RGB", (120, 120), color="blue")
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    def test_company_profile_create_with_valid_photo(self):
        response = self.client.post(
            self.url,
            {"photo": self._make_valid_jpeg(), "description": "Valid photo upload"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertIn("profile_id", response.data["data"])

    def test_company_profile_create_rejects_invalid_photo_format(self):
        invalid_file = SimpleUploadedFile(
            "logo.txt",
            b"plain text content",
            content_type="text/plain",
        )

        response = self.client.post(
            self.url,
            {"photo": invalid_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo", response.data["error"]["field_errors"])
        self.assertIn(
            "Invalid file format",
            str(response.data["error"]["field_errors"]["photo"]),
        )

    def test_company_profile_create_rejects_photo_over_5mb(self):
        from PIL import Image

        image = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        image.save(buffer, format="JPEG")

        content = buffer.getvalue()
        if len(content) <= settings.MAX_FILE_SIZE:
            content += b"\x00" * (settings.MAX_FILE_SIZE + 1 - len(content))

        large_photo = SimpleUploadedFile(
            "large_logo.jpg",
            content,
            content_type="image/jpeg",
        )

        response = self.client.post(
            self.url,
            {"photo": large_photo},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo", response.data["error"]["field_errors"])
        self.assertIn("5MB", str(response.data["error"]["field_errors"]["photo"]))
