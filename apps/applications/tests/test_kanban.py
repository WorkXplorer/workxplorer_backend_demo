"""
Tests for Kanban board functionality.

Tests the following endpoints:
- GET /api/v1/applications/kanban/ - List applications grouped by status
- PATCH /api/v1/applications/{id}/update-status/ - Update status with Kanban position
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.applications.models import (
    ApplicationStatus,
    ApplicationStatusModel,
    JobApplication,
    StatusCategory,
)
from apps.vacancies.models import Vacancy
from apps.profiles.models import RecruiterProfile, CandidateProfile


class KanbanViewTestCase(APITestCase):
    """Test cases for Kanban board views."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data that will be shared across all tests in this class."""
        # Create a company
        cls.company = Company.objects.create(
            name="Test Company",
            tin="123456789",
        )

        # Create a recruiter (admin level)
        cls.recruiter = Recruiter.objects.create_user(
            email="kanban_recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )

        # Create recruiter profile with Admin level
        cls.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Test Recruiter",
            level="Admin",
        )

        # Create another recruiter for testing (junior level)
        cls.recruiter2 = Recruiter.objects.create_user(
            email="kanban_recruiter2@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )

        # Create recruiter profile with Recruiter level (not Admin)
        cls.recruiter_profile2 = RecruiterProfile.objects.create(
            recruiter=cls.recruiter2,
            full_name="Junior Recruiter",
            level="Recruiter",
        )

        # Create candidates
        cls.candidate1 = Candidate.objects.create_user(
            email="kanban_candidate1@test.com",
            password="testpass123",
            is_candidate=True,
        )

        cls.candidate2 = Candidate.objects.create_user(
            email="kanban_candidate2@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Create candidate profiles
        cls.candidate_profile1 = CandidateProfile.objects.create(
            candidate=cls.candidate1,
            full_name="Candidate One",
        )
        cls.candidate_profile2 = CandidateProfile.objects.create(
            candidate=cls.candidate2,
            full_name="Candidate Two",
        )

        # Create a vacancy
        cls.vacancy = Vacancy.objects.create(
            title="Software Developer",
            company=cls.company,
            created_by=cls.recruiter,
            is_active=True,
            employment_type="FULL_TIME",
        )

    def setUp(self):
        """Set up test client for each test."""
        self.client = APIClient()

    def create_application(self, candidate, vacancy, status_value=ApplicationStatus.APPLIED, position=0):
        """Helper method to create a job application."""
        return JobApplication.objects.create(
            candidate=candidate,
            vacancy=vacancy,
            status=status_value,
            kanban_position=position,
        )

    def test_kanban_view_requires_authentication(self):
        """Test that the Kanban view requires authentication."""
        url = reverse("v2-kanban-applications")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_kanban_view_recruiter_access(self):
        """Test that recruiters can access the Kanban view."""
        self.client.force_authenticate(user=self.recruiter)
        url = reverse("v2-kanban-applications")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_kanban_view_returns_all_statuses(self):
        """Test that the Kanban view returns all expected status columns.

        WITHDRAWN is intentionally excluded from the kanban board in both the
        flexible-status path and the legacy fallback path — candidates withdraw
        through a dedicated endpoint and withdrawn applications are not shown
        on the recruiter's drag-and-drop board.
        """
        self.client.force_authenticate(user=self.recruiter)
        url = reverse("v2-kanban-applications")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that we have the expected status columns (WITHDRAWN excluded).
        columns = response.data["columns"]
        status_keys = [col["key"] for col in columns]

        expected_statuses = [
            choice for choice in ApplicationStatus
            if choice not in (ApplicationStatus.WITHDRAWN, ApplicationStatus.AI_FAILED)
        ]
        for status_choice in expected_statuses:
            self.assertIn(status_choice.value, status_keys)

        # WITHDRAWN must NOT appear in the kanban.
        self.assertNotIn(ApplicationStatus.WITHDRAWN.value, status_keys)

    def test_kanban_view_groups_applications_by_status(self):
        """Test that applications are grouped by status."""
        # Create applications with different statuses
        app1 = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )
        app2 = self.create_application(
            self.candidate2, self.vacancy, ApplicationStatus.INTERVIEW_SCHEDULED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("v2-kanban-applications")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Find the APPLIED column
        applied_column = next(
            (col for col in response.data["columns"] if col["key"] == "APPLIED"),
            None
        )
        self.assertIsNotNone(applied_column)
        self.assertEqual(applied_column["count"], 1)
        self.assertEqual(len(applied_column["applications"]), 1)
        self.assertEqual(
            str(applied_column["applications"][0]["id"]),
            str(app1.id)
        )

        # Find the INTERVIEW_SCHEDULED column
        interview_column = next(
            (col for col in response.data["columns"]
             if col["key"] == "INTERVIEW_SCHEDULED"),
            None
        )
        self.assertIsNotNone(interview_column)
        self.assertEqual(interview_column["count"], 1)

        # Clean up
        app1.delete()
        app2.delete()

    def test_kanban_view_pagination(self):
        """Test pagination within columns."""
        # Create multiple applications
        apps = []
        for i in range(5):
            candidate = Candidate.objects.create(
                email=f"pag_candidate{i}@test.com",
                password="testpass123",
                is_candidate=True,
            )
            app = self.create_application(
                candidate, self.vacancy, ApplicationStatus.APPLIED, i
            )
            apps.append(app)

        self.client.force_authenticate(user=self.recruiter)

        # Request with page_size=2
        url = reverse("v2-kanban-applications")
        response = self.client.get(url, {"page_size": 2, "page": 1})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_size"], 2)
        self.assertEqual(response.data["page"], 1)

        applied_column = next(
            (col for col in response.data["columns"] if col["key"] == "APPLIED"),
            None
        )
        self.assertEqual(len(applied_column["applications"]), 2)
        self.assertTrue(applied_column["has_more"])
        self.assertEqual(applied_column["count"], 5)

        # Request page 2
        response = self.client.get(url, {"page_size": 2, "page": 2})
        applied_column = next(
            (col for col in response.data["columns"] if col["key"] == "APPLIED"),
            None
        )
        self.assertEqual(len(applied_column["applications"]), 2)

        # Clean up
        for app in apps:
            app.delete()
            app.candidate.delete()

    def test_move_application_changes_status(self):
        """Test moving an application to a different status."""
        app = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("update-application-status", kwargs={"application_id": app.id})

        response = self.client.patch(url, {
            "status": "INTERVIEW_SCHEDULED",
            "kanban_position": 0,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify the application status was updated
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.INTERVIEW_SCHEDULED)
        self.assertEqual(app.kanban_position, 0)

        # Clean up
        app.delete()

    def test_move_application_reorders_within_column(self):
        """Test reordering applications within the same column."""
        app1 = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )
        app2 = self.create_application(
            self.candidate2, self.vacancy, ApplicationStatus.APPLIED, 1
        )

        self.client.force_authenticate(user=self.recruiter)

        # Move app1 to position 1 (after app2)
        url = reverse("update-application-status", kwargs={"application_id": app1.id})
        response = self.client.patch(url, {
            "status": "APPLIED",
            "kanban_position": 1,
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify positions were updated
        app1.refresh_from_db()
        app2.refresh_from_db()
        self.assertEqual(app1.kanban_position, 1)
        self.assertEqual(app2.kanban_position, 0)

        # Clean up
        app1.delete()
        app2.delete()

    def test_move_application_invalid_transition(self):
        """Test that invalid status transitions are rejected."""
        app = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.REJECTED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("update-application-status", kwargs={"application_id": app.id})

        # Try to move from REJECTED to APPLIED (invalid)
        response = self.client.patch(url, {
            "status": "APPLIED",
            "kanban_position": 0,
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verify status didn't change
        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REJECTED)

        # Clean up
        app.delete()

    def test_v2_move_application_to_another_applied_category_status(self):
        """Recruiters can move an application between different statuses in APPLIED category."""
        applied_category = StatusCategory.objects.get(key=StatusCategory.APPLIED)
        received_status = ApplicationStatusModel.objects.create(
            key="RECEIVED",
            label="Received",
            company=self.company,
            category=applied_category,
            color="#2563EB",
            position=2,
            is_default=False,
        )
        app = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("v2-update-application-status", kwargs={"application_id": app.id})

        response = self.client.patch(
            url,
            {
                "status_id": str(received_status.id),
                "kanban_position": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        app.refresh_from_db()
        self.assertEqual(app.status, received_status.key)
        self.assertEqual(received_status.category.key, StatusCategory.APPLIED)

        app.delete()

    def test_v2_archive_rejects_protected_applied_and_rejected_statuses(self):
        """Applied and Rejected base statuses must remain active and cannot be archived."""
        self.client.force_authenticate(user=self.recruiter)

        for status_key in (ApplicationStatus.APPLIED, ApplicationStatus.REJECTED):
            protected_status = ApplicationStatusModel.objects.get(
                company=self.company,
                key=status_key,
                is_active=True,
            )

            response = self.client.post(
                reverse(
                    "v2-company-status-archive",
                    kwargs={"status_id": protected_status.id},
                ),
                {},
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            protected_status.refresh_from_db()
            self.assertTrue(protected_status.is_active)

    def test_move_application_requires_notes_for_rejection(self):
        """Test that rejecting an application requires notes."""
        app = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("update-application-status", kwargs={"application_id": app.id})

        # Try to reject without notes
        response = self.client.patch(url, {
            "status": "REJECTED",
            "kanban_position": 0,
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recruiter_notes", str(response.data))

        # Clean up
        app.delete()

    def test_move_application_with_notes(self):
        """Test rejecting an application with notes."""
        app = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("update-application-status", kwargs={"application_id": app.id})

        response = self.client.patch(url, {
            "status": "REJECTED",
            "kanban_position": 0,
            "recruiter_notes": "Not a good fit for the role",
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.REJECTED)
        self.assertIn("Not a good fit", app.recruiter_notes)

        # Clean up
        app.delete()

    def test_move_application_junior_recruiter_denied(self):
        """Test that junior recruiters cannot move applications."""
        app = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )

        self.client.force_authenticate(user=self.recruiter2)  # Junior recruiter
        url = reverse("update-application-status", kwargs={"application_id": app.id})

        response = self.client.patch(url, {
            "status": "INTERVIEW_SCHEDULED",
            "kanban_position": 0,
        })

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Clean up
        app.delete()

    def test_kanban_view_filters_by_vacancy(self):
        """Test filtering Kanban by vacancy_id."""
        # Create another vacancy
        vacancy2 = Vacancy.objects.create(
            title="Another Position",
            company=self.company,
            created_by=self.recruiter,
            is_active=True,
        )

        app1 = self.create_application(
            self.candidate1, self.vacancy, ApplicationStatus.APPLIED, 0
        )
        app2 = self.create_application(
            self.candidate2, vacancy2, ApplicationStatus.APPLIED, 0
        )

        self.client.force_authenticate(user=self.recruiter)
        url = reverse("v2-kanban-applications")

        # Filter by first vacancy
        response = self.client.get(url, {"vacancy_id": str(self.vacancy.id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        applied_column = next(
            (col for col in response.data["columns"] if col["key"] == "APPLIED"),
            None
        )
        self.assertEqual(applied_column["count"], 1)
        self.assertEqual(
            str(applied_column["applications"][0]["id"]),
            str(app1.id)
        )

        # Clean up
        app1.delete()
        app2.delete()
        vacancy2.delete()
