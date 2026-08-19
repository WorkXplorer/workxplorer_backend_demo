"""
Tests for the AI evaluation signal logic (demo vs real pipeline) and
the /api/v2/applications/{id}/ai-evaluation/ endpoint.
"""
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase
from django.test import TestCase, override_settings

from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.profiles.models import RecruiterProfile, CandidateProfile
from apps.vacancies.models import Vacancy
from apps.applications.models import JobApplication, ApplicationAIEvaluation, EvaluationStatus
from apps.applications.services.demo_evaluation import DEMO_AI_EVALUATION_RESULT


def _make_company(name, tin, is_active):
    return Company.objects.create(name=name, tin=tin, is_active=is_active)


def _make_recruiter(email, company):
    r = Recruiter.objects.create_user(email=email, password="pass", is_recruiter=True)
    r.company = company
    r.save(update_fields=["company"])
    RecruiterProfile.objects.create(recruiter=r, full_name="Test Recruiter")
    return r


def _make_candidate(email):
    c = Candidate.objects.create_user(email=email, password="pass", is_candidate=True)
    CandidateProfile.objects.create(candidate=c, full_name="Test Candidate")
    return c


def _make_vacancy(recruiter, company):
    return Vacancy.objects.create(
        title="Test Vacancy",
        company=company,
        created_by=recruiter,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Signal tests
# ──────────────────────────────────────────────────────────────────────────────

# These two classes assert on the *global* transaction.on_commit queue to
# prove the AI evaluation task is (or is not) enqueued. Realtime chat also
# registers on_commit callbacks when an application creates its conversation,
# which would be counted here and read as an unexpected enqueue. Chat is off
# by default, but pinning it makes these tests independent of that default —
# they are about AI evaluation, not about whether chat is switched on.
@override_settings(CHAT_ENABLED=False)
class DemoEvaluationSignalTests(TestCase):
    """
    When a JobApplication is created for an unapproved company,
    the signal must fill in the demo evaluation immediately (status=COMPLETED)
    and must NOT enqueue the real AI evaluation task.
    """

    def setUp(self):
        self.unapproved_company = _make_company("Unapproved Co", "111111111", is_active=False)
        self.recruiter = _make_recruiter("recruiter_unapp@test.com", self.unapproved_company)
        self.candidate = _make_candidate("candidate_unapp@test.com")
        self.vacancy = _make_vacancy(self.recruiter, self.unapproved_company)

    def test_unapproved_company_gets_demo_evaluation_on_apply(self):
        with patch("apps.applications.signals.transaction.on_commit") as mock_commit:
            application = JobApplication.objects.create(
                candidate=self.candidate,
                vacancy=self.vacancy,
                status="APPLIED",
            )

        evaluation = ApplicationAIEvaluation.objects.get(application=application)
        self.assertEqual(evaluation.status, EvaluationStatus.COMPLETED)
        self.assertIsNotNone(evaluation.result)
        self.assertEqual(evaluation.overall_score, DEMO_AI_EVALUATION_RESULT["overall_score"])
        # on_commit (real AI evaluation task) must NOT have been called
        mock_commit.assert_not_called()

    def test_unapproved_evaluation_result_matches_demo_data(self):
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status="APPLIED",
        )
        evaluation = ApplicationAIEvaluation.objects.get(application=application)
        self.assertEqual(evaluation.result["recommendation"], DEMO_AI_EVALUATION_RESULT["recommendation"])
        self.assertIn("match_breakdown", evaluation.result)
        self.assertIn("skills_analysis", evaluation.result)
        self.assertIn("strengths", evaluation.result)
        self.assertIn("red_flags", evaluation.result)

    def test_unapproved_evaluation_has_evaluated_at_set(self):
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status="APPLIED",
        )
        evaluation = ApplicationAIEvaluation.objects.get(application=application)
        self.assertIsNotNone(evaluation.evaluated_at)

    def test_unapproved_evaluation_result_is_trilingual(self):
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status="APPLIED",
        )
        result = ApplicationAIEvaluation.objects.get(application=application).result
        for field in ["summary", "experience_summary", "education_summary", "activity_summary"]:
            self.assertIn("uz", result[field])
            self.assertIn("ru", result[field])
            self.assertIn("en", result[field])
        for lang in ["uz", "ru", "en"]:
            self.assertIn(lang, result["strengths"])
            self.assertIn(lang, result["red_flags"])


@override_settings(CHAT_ENABLED=False)
class ApprovedCompanyEvaluationSignalTests(TestCase):
    """
    When a JobApplication is created for an APPROVED company,
    the signal must create a PENDING evaluation and enqueue the real AI evaluation task.
    """

    def setUp(self):
        self.approved_company = _make_company("Approved Co", "222222222", is_active=True)
        self.recruiter = _make_recruiter("recruiter_app@test.com", self.approved_company)
        self.candidate = _make_candidate("candidate_app@test.com")
        self.vacancy = _make_vacancy(self.recruiter, self.approved_company)

    def test_approved_company_evaluation_starts_pending(self):
        with patch("apps.applications.signals.transaction.on_commit"):
            application = JobApplication.objects.create(
                candidate=self.candidate,
                vacancy=self.vacancy,
                status="APPLIED",
            )
        evaluation = ApplicationAIEvaluation.objects.get(application=application)
        self.assertEqual(evaluation.status, EvaluationStatus.PENDING)
        self.assertIsNone(evaluation.result)

    def test_approved_company_enqueues_real_task(self):
        enqueued = []

        def capture_commit(fn):
            enqueued.append(fn)

        with patch("apps.applications.signals.transaction.on_commit", side_effect=capture_commit):
            JobApplication.objects.create(
                candidate=self.candidate,
                vacancy=self.vacancy,
                status="APPLIED",
            )

        self.assertEqual(len(enqueued), 1, "Expected exactly one on_commit callback (RQ enqueue)")


# ──────────────────────────────────────────────────────────────────────────────
# API endpoint tests
# ──────────────────────────────────────────────────────────────────────────────

class AIEvaluationViewTests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = _make_company("API Test Co", "333333333", is_active=False)
        cls.recruiter = _make_recruiter("api_recruiter@test.com", cls.company)
        cls.candidate = _make_candidate("api_candidate@test.com")
        cls.vacancy = _make_vacancy(cls.recruiter, cls.company)
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate,
            vacancy=cls.vacancy,
            status="APPLIED",
        )
        # Fetch the evaluation created by the signal
        cls.evaluation = ApplicationAIEvaluation.objects.get(application=cls.application)

    def _url(self):
        return f"/api/v2/applications/{self.application.id}/ai-evaluation/"

    def test_requires_authentication(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_recruiter_can_view_evaluation(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_response_contains_expected_fields(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self._url())
        data = response.data["data"]
        for field in ["application_id", "status", "overall_score", "result"]:
            self.assertIn(field, data)

    def test_response_status_is_completed_for_unapproved_company(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self._url())
        self.assertEqual(response.data["data"]["status"], EvaluationStatus.COMPLETED)

    def test_response_result_has_match_breakdown(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self._url())
        result = response.data["data"]["result"]
        self.assertIn("match_breakdown", result)

    def test_candidate_cannot_view_evaluation(self):
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_wrong_recruiter_cannot_view_evaluation(self):
        other_company = _make_company("Other Co", "444444444", is_active=False)
        other_recruiter = _make_recruiter("other@test.com", other_company)
        self.client.force_authenticate(user=other_recruiter)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_nonexistent_application_returns_404(self):
        import uuid
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(f"/api/v2/applications/{uuid.uuid4()}/ai-evaluation/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ──────────────────────────────────────────────────────────────────────────────
# DEMO_AI_EVALUATION_RESULT constant tests
# ──────────────────────────────────────────────────────────────────────────────

class DemoEvaluationResultTests(TestCase):

    def test_has_overall_score(self):
        self.assertIn("overall_score", DEMO_AI_EVALUATION_RESULT)
        self.assertIsInstance(DEMO_AI_EVALUATION_RESULT["overall_score"], float)

    def test_has_average_rating(self):
        self.assertIn("average_rating", DEMO_AI_EVALUATION_RESULT)

    def test_average_rating_is_10_scale(self):
        rating = DEMO_AI_EVALUATION_RESULT["average_rating"]
        self.assertGreaterEqual(rating, 0)
        self.assertLessEqual(rating, 10)

    def test_overall_score_is_percentage(self):
        score = DEMO_AI_EVALUATION_RESULT["overall_score"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)

    def test_match_breakdown_scores_are_10_scale(self):
        for key, block in DEMO_AI_EVALUATION_RESULT["match_breakdown"].items():
            score = block.get("score")
            if score is not None:
                self.assertLessEqual(score, 10, f"{key} score should be ≤ 10")
                self.assertGreaterEqual(score, 0)

    def test_all_text_fields_are_trilingual(self):
        for field in ["summary", "experience_summary", "education_summary", "activity_summary"]:
            value = DEMO_AI_EVALUATION_RESULT[field]
            for lang in ["uz", "ru", "en"]:
                self.assertIn(lang, value, f"{field} missing '{lang}'")
                self.assertTrue(value[lang], f"{field}.{lang} is empty")

    def test_strengths_and_red_flags_are_trilingual_lists(self):
        for field in ["strengths", "red_flags"]:
            value = DEMO_AI_EVALUATION_RESULT[field]
            for lang in ["uz", "ru", "en"]:
                self.assertIn(lang, value)
                self.assertIsInstance(value[lang], list)
                self.assertGreater(len(value[lang]), 0)

    def test_skills_analysis_has_required_keys(self):
        skills = DEMO_AI_EVALUATION_RESULT["skills_analysis"]
        for key in ["matched_skills", "missing_skills", "bonus_skills"]:
            self.assertIn(key, skills)
            self.assertIsInstance(skills[key], list)
