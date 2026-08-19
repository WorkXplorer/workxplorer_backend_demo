from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.profiles.models import RecruiterProfile
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models import ApplicationStatusModel, StatusCategory
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class AIFailedCompanyCandidatesFilterTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        # Inactive companies get demo applications instead of their own rows,
        # which would make every assertion below test the demo fixture.
        cls.company = Company.objects.create(
            name="Test Company", tin="123456789", is_active=True
        )

        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Test Recruiter",
        )

        cls.vacancy = Vacancy.objects.create(
            title="Test Vacancy",
            company=cls.company,
            created_by=cls.recruiter,
        )

        # Ensure required categories and statuses exist
        cls.applied_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.APPLIED,
            defaults={"label": "Applied", "position": 1, "is_single_column": True},
        )
        cls.rejected_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.REJECTED,
            defaults={"label": "Rejected", "position": 9, "is_terminal": True, "is_single_column": True},
        )
        cls.ai_failed_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.AI_FAILED,
            defaults={"label": "AI Rejected", "position": 12, "is_single_column": True},
        )

        cls.applied_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key=ApplicationStatus.APPLIED,
            defaults={
                "label": "Applied",
                "category": cls.applied_category,
                "color": "#3B82F6",
                "position": 1,
                "is_active": True,
            },
        )
        cls.rejected_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key=ApplicationStatus.REJECTED,
            defaults={
                "label": "Rejected",
                "category": cls.rejected_category,
                "color": "#DC2626",
                "position": 2,
                "is_active": True,
                "is_default": True,
            },
        )
        cls.ai_failed_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key="AI_FAILED",
            defaults={
                "label": "AI Rejected",
                "category": cls.ai_failed_category,
                "color": "#F97316",
                "position": 3,
                "is_active": True,
                "show_in_kanban": False,
                "is_default": True,
            },
        )

        cls.candidate1 = Candidate.objects.create_user(
            email="candidate1@example.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.candidate2 = Candidate.objects.create_user(
            email="candidate2@example.com",
            password="testpass123",
            is_candidate=True,
        )

        cls.applied_app = JobApplication.objects.create(
            candidate=cls.candidate1,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=ApplicationStatus.APPLIED,
        )
        cls.ai_failed_app = JobApplication.objects.create(
            candidate=cls.candidate2,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=cls.ai_failed_status.key,
        )

    def get_url(self, **params):
        base_url = reverse("company-candidates")
        if params:
            return base_url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return base_url

    def test_ai_fail_filter_returns_only_ai_failed_applications(self):
        self.client.force_authenticate(user=self.recruiter)
        url = self.get_url(ai_fail="true")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()["data"]
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], str(self.ai_failed_app.id))

    def test_company_applications_summary_hides_ai_failed(self):
        """
        The per-row dropdown mirrors the tab it is opened from: AI-rejected
        applications belong to the AI-rejected tab, so the general listing
        must neither count nor list them.
        """
        other_vacancy = Vacancy.objects.create(
            title="Another Vacancy",
            company=self.company,
            created_by=self.recruiter,
        )
        JobApplication.objects.create(
            candidate=self.candidate1,
            vacancy=other_vacancy,
            applied_at=timezone.now() - timedelta(days=1),
            status=self.ai_failed_status.key,
        )
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.get_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(
            r for r in response.json()["data"] if r["id"] == str(self.applied_app.id)
        )
        summary = row["company_applications"]
        self.assertEqual(summary["total_count"], 1)
        self.assertEqual(
            [entry["status"] for entry in summary["applications"]],
            [ApplicationStatus.APPLIED],
        )

    def test_company_applications_summary_on_ai_fail_tab_lists_only_ai_failed(self):
        """On the AI-rejected tab the dropdown shows only those applications."""
        other_vacancy = Vacancy.objects.create(
            title="Another Vacancy",
            company=self.company,
            created_by=self.recruiter,
        )
        JobApplication.objects.create(
            candidate=self.candidate2,
            vacancy=other_vacancy,
            applied_at=timezone.now() - timedelta(days=1),
            status=ApplicationStatus.APPLIED,
        )
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.get_url(ai_fail="true"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(
            r for r in response.json()["data"] if r["id"] == str(self.ai_failed_app.id)
        )
        summary = row["company_applications"]
        self.assertEqual(summary["total_count"], 1)
        self.assertEqual(
            [entry["application_id"] for entry in summary["applications"]],
            [str(self.ai_failed_app.id)],
        )


class AIRevaluationAPITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Test Company", tin="123456789")

        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Test Recruiter",
        )

        cls.other_company = Company.objects.create(name="Other Company", tin="987654321")
        cls.other_recruiter = Recruiter.objects.create_user(
            email="other@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.other_company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.other_recruiter,
            full_name="Other Recruiter",
        )

        cls.vacancy = Vacancy.objects.create(
            title="Test Vacancy",
            company=cls.company,
            created_by=cls.recruiter,
        )

        cls.applied_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.APPLIED,
            defaults={"label": "Applied", "position": 1, "is_single_column": True},
        )
        cls.rejected_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.REJECTED,
            defaults={"label": "Rejected", "position": 9, "is_terminal": True, "is_single_column": True},
        )
        cls.ai_failed_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.AI_FAILED,
            defaults={"label": "AI Rejected", "position": 12, "is_single_column": True},
        )

        cls.applied_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key=ApplicationStatus.APPLIED,
            defaults={
                "label": "Applied",
                "category": cls.applied_category,
                "color": "#3B82F6",
                "position": 1,
                "is_active": True,
            },
        )
        cls.rejected_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key=ApplicationStatus.REJECTED,
            defaults={
                "label": "Rejected",
                "category": cls.rejected_category,
                "color": "#DC2626",
                "position": 2,
                "is_active": True,
                "is_default": True,
            },
        )
        cls.ai_failed_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key="AI_FAILED",
            defaults={
                "label": "AI Rejected",
                "category": cls.ai_failed_category,
                "color": "#F97316",
                "position": 3,
                "is_active": True,
                "show_in_kanban": False,
                "is_default": True,
            },
        )

        cls.candidate1 = Candidate.objects.create_user(
            email="candidate1@example.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.candidate2 = Candidate.objects.create_user(
            email="candidate2@example.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.candidate3 = Candidate.objects.create_user(
            email="candidate3@example.com",
            password="testpass123",
            is_candidate=True,
        )

        cls.ai_failed_app1 = JobApplication.objects.create(
            candidate=cls.candidate1,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=cls.ai_failed_status.key,
        )
        cls.ai_failed_app2 = JobApplication.objects.create(
            candidate=cls.candidate2,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=cls.ai_failed_status.key,
        )
        cls.applied_app = JobApplication.objects.create(
            candidate=cls.candidate3,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=ApplicationStatus.APPLIED,
        )

        cls.url = reverse("v2-ai-revaluation")

    def test_move_ai_failed_to_applied(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(
            self.url,
            {
                "application_ids": [str(self.ai_failed_app1.id)],
                "reject": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ai_failed_app1.refresh_from_db()
        self.assertEqual(self.ai_failed_app1.status, ApplicationStatus.APPLIED)

    def test_move_ai_failed_to_rejected(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(
            self.url,
            {
                "application_ids": [str(self.ai_failed_app2.id)],
                "reject": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ai_failed_app2.refresh_from_db()
        self.assertEqual(self.ai_failed_app2.status, ApplicationStatus.REJECTED)

    def test_bulk_move_applications(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(
            self.url,
            {
                "application_ids": [
                    str(self.ai_failed_app1.id),
                    str(self.ai_failed_app2.id),
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["updated_count"], 2)

    def test_error_if_application_not_in_ai_failed(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(
            self.url,
            {"application_ids": [str(self.applied_app.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_error_if_application_from_other_company(self):
        other_candidate = Candidate.objects.create_user(
            email="other-candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )
        other_vacancy = Vacancy.objects.create(
            title="Other Vacancy",
            company=self.other_company,
            created_by=self.other_recruiter,
        )
        other_app = JobApplication.objects.create(
            candidate=other_candidate,
            vacancy=other_vacancy,
            applied_at=timezone.now(),
            status=self.ai_failed_status.key,
        )
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(
            self.url,
            {"application_ids": [str(other_app.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AIFailedTransitionValidationTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Test Company", tin="123456789", is_active=True
        )

        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Test Recruiter",
        )

        cls.vacancy = Vacancy.objects.create(
            title="Test Vacancy",
            company=cls.company,
            created_by=cls.recruiter,
        )

        cls.applied_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.APPLIED,
            defaults={"label": "Applied", "position": 1, "is_single_column": True},
        )
        cls.ai_failed_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.AI_FAILED,
            defaults={"label": "AI Rejected", "position": 12, "is_single_column": True},
        )
        cls.withdrawn_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.WITHDRAWN,
            defaults={"label": "Withdrawn", "position": 10, "is_terminal": True, "is_single_column": True},
        )

        cls.applied_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key=ApplicationStatus.APPLIED,
            defaults={
                "label": "Applied",
                "category": cls.applied_category,
                "color": "#3B82F6",
                "position": 1,
                "is_active": True,
            },
        )
        cls.ai_failed_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key="AI_FAILED",
            defaults={
                "label": "AI Rejected",
                "category": cls.ai_failed_category,
                "color": "#F97316",
                "position": 2,
                "is_active": True,
                "show_in_kanban": False,
                "is_default": True,
            },
        )
        cls.withdrawn_status, _ = ApplicationStatusModel.objects.update_or_create(
            company=cls.company,
            key=ApplicationStatus.WITHDRAWN,
            defaults={
                "label": "Withdrawn",
                "category": cls.withdrawn_category,
                "color": "#6B7280",
                "position": 3,
                "is_active": True,
            },
        )

        cls.candidate = Candidate.objects.create_user(
            email="candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )

        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            applied_at=timezone.now(),
            status=ApplicationStatus.APPLIED,
        )

        cls.url = reverse(
            "update-application-status",
            kwargs={"application_id": cls.application.id},
        )
        cls.withdraw_url = reverse(
            "withdraw-application",
            kwargs={"application_id": cls.application.id},
        )

    def test_cannot_move_to_ai_failed_via_update_status(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self.url,
            {"status": "AI_FAILED"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.application.refresh_from_db()
        self.assertNotEqual(self.application.status, "AI_FAILED")

    def test_recruiter_can_move_from_ai_failed_to_applied(self):
        self.application.status = "AI_FAILED"
        self.application.save()

        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.APPLIED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPLIED)

    def test_recruiter_cannot_move_ai_failed_to_withdrawn(self):
        self.application.status = "AI_FAILED"
        self.application.save()

        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self.url,
            {"status": ApplicationStatus.WITHDRAWN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "AI_FAILED")

    def test_candidate_can_withdraw_from_ai_failed(self):
        self.application.status = "AI_FAILED"
        self.application.save()

        self.client.force_authenticate(user=self.candidate)
        response = self.client.patch(self.withdraw_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.WITHDRAWN)
