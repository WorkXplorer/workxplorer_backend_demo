"""
Tests for the candidate ↔ company applications aggregation feature:

- CandidateCompanyApplicationsService (shared logic)
- GET /applications/company-candidates/<candidate_id>/applications/ (v1, list detail)
- GET /api/v2/applications/kanban/candidates/<candidate_id>/applications/ (v2, kanban detail)
- company_applications summary embedded in the candidates list response only
  (kanban cards deliberately do not carry it)
"""

from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.profiles.models import RecruiterProfile
from apps.vacancies.models import Vacancy
from apps.applications.models import ApplicationAIEvaluation, EvaluationStatus
from apps.applications.models.applications import JobApplication
from apps.applications.models.choices import ApplicationStatus
from apps.applications.services.candidate_company_applications import (
    CandidateCompanyApplicationsService,
)


class CandidateCompanyApplicationsTestBase(APITestCase):
    """Shared fixtures: two companies, recruiters, one candidate with 4 applications."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Company 1", tin="111111111", is_active=True
        )
        cls.other_company = Company.objects.create(
            name="Company 2", tin="222222222", is_active=True
        )

        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter1@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        cls.second_recruiter = Recruiter.objects.create_user(
            email="recruiter1b@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        cls.other_recruiter = Recruiter.objects.create_user(
            email="recruiter2@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.other_company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter, full_name="Alisher Baltabaev"
        )
        RecruiterProfile.objects.create(
            recruiter=cls.second_recruiter, full_name="Abdukodir Khusanov"
        )
        RecruiterProfile.objects.create(
            recruiter=cls.other_recruiter, full_name="Other Recruiter"
        )

        cls.vacancy_senior = Vacancy.objects.create(
            title="Senior UX/UI Designer",
            company=cls.company,
            created_by=cls.recruiter,
        )
        cls.vacancy_product = Vacancy.objects.create(
            title="Product Designer",
            company=cls.company,
            created_by=cls.second_recruiter,
        )
        cls.vacancy_junior = Vacancy.objects.create(
            title="Junior Visual Designer",
            company=cls.company,
            created_by=cls.recruiter,
        )
        cls.vacancy_withdrawn = Vacancy.objects.create(
            title="Withdrawn Vacancy",
            company=cls.company,
            created_by=cls.recruiter,
        )
        cls.other_vacancy = Vacancy.objects.create(
            title="Other Company Vacancy",
            company=cls.other_company,
            created_by=cls.other_recruiter,
        )

        cls.candidate = Candidate.objects.create_user(
            email="candidate1@example.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.lonely_candidate = Candidate.objects.create_user(
            email="candidate2@example.com",
            password="testpass123",
            is_candidate=True,
        )

        # Best match: score 98, OFFERED
        cls.app_senior = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy_senior,
            status=ApplicationStatus.OFFERED,
        )
        # A post_save signal auto-creates a pending evaluation — update it.
        ApplicationAIEvaluation.objects.filter(application=cls.app_senior).update(
            status=EvaluationStatus.COMPLETED,
            overall_score=98.0,
        )

        # Second: score 84, INTERVIEW_SCHEDULED
        cls.app_product = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy_product,
            status=ApplicationStatus.INTERVIEW_SCHEDULED,
        )
        ApplicationAIEvaluation.objects.filter(application=cls.app_product).update(
            status=EvaluationStatus.COMPLETED,
            overall_score=84.0,
        )

        # Third: no AI evaluation yet — must sort last
        cls.app_junior = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy_junior,
            status=ApplicationStatus.APPLIED,
        )

        # Withdrawn — must be excluded everywhere
        cls.app_withdrawn = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy_withdrawn,
            status=ApplicationStatus.WITHDRAWN,
        )

        # Application to another company — must never leak
        cls.app_other_company = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.other_vacancy,
            status=ApplicationStatus.APPLIED,
        )

    def login_recruiter(self, recruiter=None):
        self.client.force_authenticate(user=recruiter or self.recruiter)


class CandidateCompanyApplicationsServiceTests(CandidateCompanyApplicationsTestBase):
    """Unit tests for the shared service."""

    def test_salary_formatting_preserves_cents(self):
        """
        Whole-number salaries render without decimals, but fractional ones
        (e.g. an hourly rate of 45.50) must keep their cents instead of
        being rounded to the nearest whole unit.
        """
        from decimal import Decimal

        self.vacancy_senior.salary_min = Decimal("45.50")
        self.vacancy_senior.salary_max = None
        self.vacancy_senior.salary_currency = "USD"

        salary = CandidateCompanyApplicationsService._format_vacancy_salary(
            self.vacancy_senior
        )
        self.assertEqual(salary, "45.50 USD")

        self.vacancy_senior.salary_min = Decimal("1000")
        salary = CandidateCompanyApplicationsService._format_vacancy_salary(
            self.vacancy_senior
        )
        self.assertEqual(salary, "1,000 USD")

    def test_detail_orders_by_ai_score_desc_with_nulls_last(self):
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.candidate.id
        )
        self.assertIsNotNone(data)
        titles = [entry["vacancy_title"] for entry in data["applications"]]
        self.assertEqual(
            titles,
            ["Senior UX/UI Designer", "Product Designer", "Junior Visual Designer"],
        )
        scores = [entry["ai_score"] for entry in data["applications"]]
        self.assertEqual(scores, [98.0, 84.0, None])

    def test_detail_excludes_withdrawn_and_other_companies(self):
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.candidate.id
        )
        self.assertEqual(data["total_count"], 3)
        titles = {entry["vacancy_title"] for entry in data["applications"]}
        self.assertNotIn("Withdrawn Vacancy", titles)
        self.assertNotIn("Other Company Vacancy", titles)

    def test_only_first_entry_is_best_match(self):
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.candidate.id
        )
        flags = [entry["is_best_match"] for entry in data["applications"]]
        self.assertEqual(flags, [True, False, False])

    def test_entry_contains_recruiter_from_vacancy_created_by(self):
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.candidate.id
        )
        best = data["applications"][0]
        self.assertEqual(best["recruiter"]["full_name"], "Alisher Baltabaev")
        self.assertEqual(best["recruiter"]["id"], str(self.recruiter.id))
        second = data["applications"][1]
        self.assertEqual(second["recruiter"]["full_name"], "Abdukodir Khusanov")

    def test_applied_at_uses_dd_mm_yyyy_format(self):
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.candidate.id
        )
        for entry in data["applications"]:
            self.assertRegex(entry["applied_at"], r"^\d{2}\.\d{2}\.\d{4}$")

    def test_ai_passed_respects_vacancy_threshold(self):
        # default minimum_ai_score is 40: 98 → passed, 84 → passed, None → None
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.candidate.id
        )
        passed = [entry["ai_passed"] for entry in data["applications"]]
        self.assertEqual(passed, [True, True, None])

    def test_returns_none_for_candidate_without_applications(self):
        data = CandidateCompanyApplicationsService.get_candidate_applications(
            self.company, self.lonely_candidate.id
        )
        self.assertIsNone(data)

    def test_summary_map_counts_and_best_match(self):
        summary = CandidateCompanyApplicationsService.get_summary_map(
            self.company, [self.candidate.id, self.lonely_candidate.id]
        )
        self.assertIn(self.candidate.id, summary)
        self.assertNotIn(self.lonely_candidate.id, summary)

        candidate_summary = summary[self.candidate.id]
        self.assertEqual(candidate_summary["total_count"], 3)
        # Full list is returned, best match first.
        self.assertEqual(len(candidate_summary["applications"]), 3)
        best = candidate_summary["applications"][0]
        self.assertEqual(best["vacancy_title"], "Senior UX/UI Designer")
        self.assertEqual(best["ai_score"], 98.0)
        self.assertEqual(best["status"], ApplicationStatus.OFFERED)
        self.assertTrue(best["is_best_match"])

    def test_summary_map_empty_input(self):
        self.assertEqual(
            CandidateCompanyApplicationsService.get_summary_map(self.company, []),
            {},
        )


class CompanyCandidateApplicationsAPITests(CandidateCompanyApplicationsTestBase):
    """Tests for the v1 (candidates list) detail endpoint."""

    def get_url(self, candidate_id):
        return reverse(
            "company-candidate-applications", kwargs={"candidate_id": candidate_id}
        )

    def test_recruiter_gets_candidate_applications(self):
        self.login_recruiter()
        response = self.client.get(self.get_url(self.candidate.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 3)
        self.assertEqual(response.data["candidate_id"], str(self.candidate.id))
        self.assertEqual(
            response.data["applications"][0]["vacancy_title"], "Senior UX/UI Designer"
        )

    def test_other_company_recruiter_gets_404(self):
        self.login_recruiter(self.other_recruiter)
        # candidate applied to other_company too, so scope down to a candidate
        # visible only in company 1: use lonely candidate + candidate's company-1-only data
        response = self.client.get(self.get_url(self.lonely_candidate.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_company_recruiter_sees_only_own_company_applications(self):
        self.login_recruiter(self.other_recruiter)
        response = self.client.get(self.get_url(self.candidate.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(
            response.data["applications"][0]["vacancy_title"], "Other Company Vacancy"
        )

    def test_candidate_cannot_access(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.get_url(self.candidate.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_access(self):
        response = self.client.get(self.get_url(self.candidate.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_candidate_returns_404(self):
        self.login_recruiter()
        import uuid

        response = self.client.get(self.get_url(uuid.uuid4()))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class KanbanCandidateApplicationsAPITests(CandidateCompanyApplicationsTestBase):
    """Tests for the v2 (kanban) detail endpoint — same payload, own URL."""

    def get_url(self, candidate_id):
        return reverse(
            "v2-kanban-candidate-applications", kwargs={"candidate_id": candidate_id}
        )

    def test_recruiter_gets_candidate_applications(self):
        self.login_recruiter()
        response = self.client.get(self.get_url(self.candidate.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 3)
        scores = [entry["ai_score"] for entry in response.data["applications"]]
        self.assertEqual(scores, [98.0, 84.0, None])

    def test_candidate_cannot_access(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.get_url(self.candidate.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CompanyCandidatesListSummaryTests(CandidateCompanyApplicationsTestBase):
    """The candidates list rows must carry the company_applications summary."""

    def test_list_rows_include_summary(self):
        self.login_recruiter()
        response = self.client.get(reverse("company-candidates"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]
        self.assertTrue(results)
        row = next(
            r for r in results if r["candidate_email"] == "candidate1@example.com"
        )
        summary = row["company_applications"]
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total_count"], 3)
        self.assertEqual(len(summary["applications"]), 3)
        self.assertEqual(summary["applications"][0]["ai_score"], 98.0)
        self.assertEqual(
            summary["applications"][0]["vacancy_title"], "Senior UX/UI Designer"
        )

    def test_best_match_alias_kept_for_existing_consumers(self):
        """
        summary["best_match"] must still mirror applications[0] so any
        deployed frontend reading the old single-object shape keeps working.
        """
        self.login_recruiter()
        response = self.client.get(reverse("company-candidates"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]
        row = next(
            r for r in results if r["candidate_email"] == "candidate1@example.com"
        )
        summary = row["company_applications"]
        self.assertEqual(summary["best_match"], summary["applications"][0])


class KanbanSummaryTests(CandidateCompanyApplicationsTestBase):
    """Kanban cards must not carry the company_applications summary."""

    def test_kanban_cards_exclude_summary(self):
        self.login_recruiter()
        response = self.client.get(reverse("v2-kanban-applications"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        cards = [
            app
            for column in response.data["columns"]
            for app in column["applications"]
        ]
        self.assertTrue(cards)
        for card in cards:
            self.assertNotIn("company_applications", card)
