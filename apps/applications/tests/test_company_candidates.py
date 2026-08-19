from django.utils import timezone
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework import status
from rest_framework.test import APITestCase

from apps.vacancies.models import Vacancy
from apps.resumes.models import Resume, ResumeSkill
from apps.skills.models import Skill
from apps.authentication.models import Candidate
from apps.profiles.models import RecruiterProfile
from apps.resumes.models.choices import ProficiencyLevel
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models import ApplicationStatusModel, StatusCategory
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Company, Recruiter


class CompanyCandidatesListViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company1 = Company.objects.create(name="Company 1", tin="111111111")
        cls.company2 = Company.objects.create(name="Company 2", tin="222222222")

        cls.recruiter1 = Recruiter.objects.create_user(
            email="recruiter1@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company1,
        )
        cls.recruiter2 = Recruiter.objects.create_user(
            email="recruiter2@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company2,
        )
        cls.recruiter_profile1 = RecruiterProfile.objects.create(
            recruiter=cls.recruiter1,
            full_name="Recruiter One",
        )
        cls.recruiter_profile2 = RecruiterProfile.objects.create(
            recruiter=cls.recruiter2,
            full_name="Recruiter Two",
        )

        cls.vacancy1 = Vacancy.objects.create(
            title="Vacancy 1",
            company=cls.company1,
            created_by=cls.recruiter1,
        )
        cls.vacancy2 = Vacancy.objects.create(
            title="Vacancy 2",
            company=cls.company2,
            created_by=cls.recruiter2,
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

        cls.application1 = JobApplication.objects.create(
            candidate=cls.candidate1,
            vacancy=cls.vacancy1,
            applied_at=timezone.now(),
        )
        cls.application2 = JobApplication.objects.create(
            candidate=cls.candidate2,
            vacancy=cls.vacancy2,
            applied_at=timezone.now(),
        )

    def get_url(self, vacancy_id=None):
        base_url = reverse("company-candidates")
        if vacancy_id:
            return f"{base_url}?vacancy_id={vacancy_id}"
        return base_url

    @staticmethod
    def get_payload(response):
        return response.json()["data"]

    @staticmethod
    def get_pagination(response):
        return response.json()["pagination"]

    def test_requires_authentication(self):
        url = self.get_url(self.vacancy1.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_recruiters_can_access(self):
        self.client.force_authenticate(user=self.candidate1)
        url = self.get_url(self.vacancy1.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_recruiter_can_see_own_vacancy_applications(self):
        self.client.force_authenticate(user=self.recruiter1)
        url = self.get_url(self.vacancy1.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = self.get_payload(response)
        pagination = self.get_pagination(response)
        self.assertEqual(pagination["count"], 1)
        self.assertEqual(payload[0]["id"], str(self.application1.id))

    def test_recruiter_cannot_see_other_company_vacancy(self):
        self.client.force_authenticate(user=self.recruiter1)
        url = self.get_url(self.vacancy2.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = self.get_payload(response)
        pagination = self.get_pagination(response)
        self.assertEqual(pagination["count"], 0)
        self.assertEqual(payload, [])

    def test_invalid_vacancy_id_returns_error(self):
        self.client.force_authenticate(user=self.recruiter1)
        url = reverse("company-candidates") + "?vacancy_id=invalid-uuid"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recruiter_can_see_all_company_applications_without_vacancy_id(self):
        self.client.force_authenticate(user=self.recruiter1)
        url = self.get_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = self.get_payload(response)
        pagination = self.get_pagination(response)
        self.assertEqual(pagination["count"], 1)
        self.assertEqual(payload[0]["id"], str(self.application1.id))

    def test_company_candidates_returns_flat_status_fields(self):
        applied_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.APPLIED,
            defaults={"label": "Applied", "position": 1},
        )
        ApplicationStatusModel.objects.update_or_create(
            company=self.company1,
            key=ApplicationStatus.APPLIED,
            defaults={
                "label": "Applied",
                "category": applied_category,
                "color": "#6172F3",
                "position": 1,
                "is_active": True,
            },
        )

        self.client.force_authenticate(user=self.recruiter1)
        response = self.client.get(self.get_url(self.vacancy1.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = self.get_payload(response)
        self.assertEqual(payload[0]["status"], ApplicationStatus.APPLIED)
        self.assertEqual(payload[0]["status_display"], "Applied")
        self.assertEqual(payload[0]["status_category"], StatusCategory.APPLIED)
        self.assertEqual(payload[0]["status_color"], "#6172F3")

    def test_company_candidates_does_not_repeat_resume_skill_queries(self):
        skill = Skill.objects.create(name="Python")

        for index in range(5):
            candidate = Candidate.objects.create_user(
                email=f"bulk-candidate-{index}@example.com",
                password="testpass123",
                is_candidate=True,
            )
            resume = Resume.objects.create(
                candidate=candidate,
                title=f"Resume {index}",
                description="Experienced developer",
            )
            ResumeSkill.objects.create(
                resume=resume,
                skill=skill,
                minimum_years=3,
                proficiency_level=ProficiencyLevel.ADVANCED,
            )
            JobApplication.objects.create(
                candidate=candidate,
                vacancy=self.vacancy1,
                resume_used=resume,
                applied_at=timezone.now(),
                status=ApplicationStatus.APPLIED,
            )

        self.client.force_authenticate(user=self.recruiter1)
        url = self.get_url()

        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(
            len(captured_queries),
            18,
            msg=f"Unexpected query count: {len(captured_queries)}",
        )

    def test_company_candidates_fetches_status_metadata_once(self):
        for index, application_status in enumerate(
            [
                ApplicationStatus.APPLIED,
                ApplicationStatus.REJECTED,
                ApplicationStatus.OFFERED,
                ApplicationStatus.INTERVIEWED,
            ],
            start=1,
        ):
            candidate = Candidate.objects.create_user(
                email=f"status-bulk-candidate-{index}@example.com",
                password="testpass123",
                is_candidate=True,
            )
            JobApplication.objects.create(
                candidate=candidate,
                vacancy=self.vacancy1,
                applied_at=timezone.now(),
                status=application_status,
            )

        self.client.force_authenticate(user=self.recruiter1)

        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        status_queries = [
            query["sql"]
            for query in captured_queries.captured_queries
            if '"applications_applicationstatusmodel"' in query["sql"]
        ]
        self.assertEqual(
            len(status_queries),
            1,
            msg="Expected a single batched ApplicationStatusModel query, got: "
            + "\n".join(status_queries),
        )

    def test_company_candidates_fetches_recruiter_profiles_once(self):
        for index in range(4):
            candidate = Candidate.objects.create_user(
                email=f"recruiter-name-candidate-{index}@example.com",
                password="testpass123",
                is_candidate=True,
            )
            JobApplication.objects.create(
                candidate=candidate,
                vacancy=self.vacancy1,
                applied_at=timezone.now(),
                status=ApplicationStatus.APPLIED,
            )

        self.client.force_authenticate(user=self.recruiter1)

        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        recruiter_profile_queries = [
            query["sql"]
            for query in captured_queries.captured_queries
            if '"profiles_recruiterprofile"' in query["sql"]
        ]
        self.assertEqual(
            len(recruiter_profile_queries),
            1,
            msg="Expected a single batched RecruiterProfile query, got: "
            + "\n".join(recruiter_profile_queries),
        )

    def test_company_candidates_avoids_status_category_n_plus_one(self):
        applied_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.APPLIED,
            defaults={"label": "Applied", "position": 1},
        )
        offered_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.OFFERED,
            defaults={"label": "Offered", "position": 2},
        )
        rejected_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.REJECTED,
            defaults={"label": "Rejected", "position": 3, "is_terminal": True},
        )

        ApplicationStatusModel.objects.update_or_create(
            company=self.company1,
            key=ApplicationStatus.APPLIED,
            defaults={
                "label": "Applied",
                "category": applied_category,
                "position": 1,
                "is_active": True,
            },
        )
        ApplicationStatusModel.objects.update_or_create(
            company=self.company1,
            key=ApplicationStatus.OFFERED,
            defaults={
                "label": "Offered",
                "category": offered_category,
                "position": 2,
                "is_active": True,
            },
        )
        ApplicationStatusModel.objects.update_or_create(
            company=self.company1,
            key=ApplicationStatus.REJECTED,
            defaults={
                "label": "Rejected",
                "category": rejected_category,
                "position": 3,
                "is_active": True,
            },
        )

        for index, application_status in enumerate(
            [
                ApplicationStatus.APPLIED,
                ApplicationStatus.OFFERED,
                ApplicationStatus.REJECTED,
            ],
            start=1,
        ):
            candidate = Candidate.objects.create_user(
                email=f"status-category-candidate-{index}@example.com",
                password="testpass123",
                is_candidate=True,
            )
            JobApplication.objects.create(
                candidate=candidate,
                vacancy=self.vacancy1,
                applied_at=timezone.now(),
                status=application_status,
            )

        self.client.force_authenticate(user=self.recruiter1)

        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        standalone_status_category_queries = [
            query["sql"]
            for query in captured_queries.captured_queries
            if 'FROM "applications_statuscategory"' in query["sql"]
            and '"applications_applicationstatusmodel"' not in query["sql"]
        ]
        self.assertEqual(
            standalone_status_category_queries,
            [],
            msg="Unexpected standalone StatusCategory queries: "
            + "\n".join(standalone_status_category_queries),
        )

    def test_company_candidates_avoids_skill_n_plus_one_queries(self):
        shared_skill = Skill.objects.create(name="Python")

        for index in range(4):
            candidate = Candidate.objects.create_user(
                email=f"skill-n-plus-one-{index}@example.com",
                password="testpass123",
                is_candidate=True,
            )
            resume = Resume.objects.create(
                candidate=candidate,
                title=f"Skill Resume {index}",
                description="Backend developer",
            )
            ResumeSkill.objects.create(
                resume=resume,
                skill=shared_skill,
                minimum_years=2,
                proficiency_level=ProficiencyLevel.ADVANCED,
            )
            JobApplication.objects.create(
                candidate=candidate,
                vacancy=self.vacancy1,
                resume_used=resume,
                applied_at=timezone.now(),
                status=ApplicationStatus.APPLIED,
            )

        self.client.force_authenticate(user=self.recruiter1)

        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(self.get_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        standalone_skill_queries = [
            query["sql"]
            for query in captured_queries.captured_queries
            if 'FROM "skills_skill"' in query["sql"]
            and 'JOIN "skills_skill"' not in query["sql"]
        ]
        self.assertEqual(
            standalone_skill_queries,
            [],
            msg="Unexpected standalone Skill queries: "
            + "\n".join(standalone_skill_queries),
        )
