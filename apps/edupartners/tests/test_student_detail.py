import uuid
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from django.test import override_settings

from rest_framework.test import APITestCase
from rest_framework import status

from apps.edupartners.models import EduPartner, EduPartnersType, Faculty
from apps.profiles.models import CandidateProfile
from apps.authentication.models import Candidate
from apps.resumes.models import Resume
from apps.applications.models import JobApplication
from apps.vacancies.models import Vacancy
from apps.authentication.models import Company, Recruiter


@override_settings(EDUPARTNER_SERVICE_KEY="test-service-key")
class StudentDetailAPITests(APITestCase):
    """Test StudentDetailAPIView with nested sections."""

    @classmethod
    def setUpTestData(cls):
        cls.edupartner_type = EduPartnersType.objects.create(name="University")
        cls.edupartner = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Test University",
            edupartner_type=cls.edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
            is_active=True,
        )
        cls.faculty = Faculty.objects.create(
            name="Computer Science",
            edupartner=cls.edupartner,
        )

        # Create candidate with complete onboarding
        cls.candidate = Candidate.objects.create(
            email="test@example.com",
            date_joined=timezone.now() - timedelta(days=60),
            last_login=timezone.now() - timedelta(days=5),
            faculty=cls.faculty,
            edupartner=cls.edupartner,
            onboarding_progress={
                "create_profile": (timezone.now() - timedelta(days=30)).isoformat(),
                "create_resume": (timezone.now() - timedelta(days=28)).isoformat(),
                "vacancy_apply": (timezone.now() - timedelta(days=25)).isoformat(),
            },
        )
        cls.profile = CandidateProfile.objects.create(
            candidate=cls.candidate,
            full_name="Test Student",
            phone="+998901234567",
        )

        # Create company and vacancy
        cls.company = Company.objects.create(name="Test Company")
        cls.recruiter = Recruiter.objects.create(
            email="recruiter@test.com",
            company=cls.company,
        )
        cls.vacancy = Vacancy.objects.create(
            title="Junior Developer",
            company=cls.company,
            created_by=cls.recruiter,
        )

        # Create application
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            status="APPLIED",
        )

        cls.url = reverse("student-detail", kwargs={"pk": cls.profile.id})
        cls.auth_header = {"HTTP_X_SERVICE_KEY": "test-service-key"}

    def _get(self, query_params=None):
        params = query_params or {"edupartner_id": self.edupartner.id}
        return self.client.get(self.url, params, **self.auth_header)

    def test_detail_returns_nested_sections(self):
        """Response should contain all 5 sections."""
        response = self._get()
        assert response.status_code == status.HTTP_200_OK

        data = response.json()["data"]
        assert "activity" in data
        assert "profile" in data
        assert "applications" in data
        assert "interviews" in data
        assert "employment" in data

    def test_activity_section(self):
        """Activity section should have correct fields."""
        response = self._get()
        activity = response.json()["data"]["activity"]

        assert "registration_status" in activity
        assert "first_login" in activity
        assert "last_login_days_ago" in activity
        assert activity["activity_7d"] is True   # last login 5 days ago
        assert activity["activity_30d"] is True
        assert activity["activity_90d"] is True

    def test_activity_registration_status(self):
        """registration_status should be 'registered' when onboarding is complete."""
        # Only 3/4 steps done → in_progress
        response = self._get()
        assert response.json()["data"]["activity"]["registration_status"] == "in_progress"

        # Complete all 4 steps
        candidate = self.candidate
        candidate.onboarding_progress["verify_vault"] = timezone.now().isoformat()
        candidate.save(update_fields=["onboarding_progress"])

        response = self._get()
        assert response.json()["data"]["activity"]["registration_status"] == "registered"

    def test_profile_section(self):
        """Profile section should have basic info."""
        response = self._get()
        profile = response.json()["data"]["profile"]

        assert profile["email"] == "test@example.com"
        assert profile["phone"] == "+998901234567"
        assert profile["faculty"] == "Computer Science"
        assert profile["has_resume"] is False

    def test_profile_with_resume(self):
        """Profile should show resume info when resume exists."""
        Resume.objects.create(
            candidate=self.candidate,
            title="My Resume",
            position="Backend Developer",
            description="Test",
            is_reviewed=True,
            is_main=True,
        )
        response = self._get()
        profile = response.json()["data"]["profile"]

        assert profile["has_resume"] is True
        assert profile["career_goal"] == "Backend Developer"

    def test_applications_section(self):
        """Applications section should list applications with source."""
        response = self._get()
        applications = response.json()["data"]["applications"]

        assert len(applications) == 1
        assert applications[0]["title"] == "Junior Developer"
        assert applications[0]["company"] == "Test Company"
        assert applications[0]["source"] == "Самостоятельно"

    def test_application_source_recommended(self):
        """Application updated by recruiter should show 'Рекомендация ЦК'."""
        self.application.last_updated_by = self.recruiter
        self.application.save(update_fields=["last_updated_by"])

        response = self._get()
        applications = response.json()["data"]["applications"]

        assert applications[0]["source"] == "Рекомендация ЦК"

    def test_interviews_section_empty(self):
        """Interviews should be empty when no interview-stage applications."""
        response = self._get()
        interviews = response.json()["data"]["interviews"]

        assert interviews["count"] == 0
        assert interviews["result"] is None

    def test_employment_section_empty(self):
        """Employment should show not employed when no hired applications."""
        response = self._get()
        employment = response.json()["data"]["employment"]

        assert employment["is_employed"] is False
        assert employment["history"] == []

    def test_requires_auth(self):
        """Request without service key should return 403."""
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_wrong_edupartner_returns_404(self):
        """Request with wrong edupartner_id should return 404."""
        response = self._get(query_params={"edupartner_id": str(uuid.uuid4())})
        assert response.status_code == status.HTTP_404_NOT_FOUND
