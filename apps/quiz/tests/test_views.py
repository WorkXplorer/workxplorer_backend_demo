from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.quiz.models import Question, AnswerChoice, CareerOption, Quiz, QuizType, QuizResult
from apps.authentication.models import Candidate
from apps.domain.models import Domain
from apps.profiles.models import CandidateProfile


class QuizTypeListAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("quiz-type-list")
        QuizType.objects.create(name="Active Quiz Type", is_active=True)
        QuizType.objects.create(name="Inactive Quiz Type", is_active=False)

    def test_returns_api_response_wrapper(self):
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["success"] is True
        assert "data" in payload
        results = payload["data"]["results"]
        assert [item["name"] for item in results] == ["Active Quiz Type"]


class QuestionListAPITests(APITestCase):
    """
    Test suite for the Question List API.

    This endpoint should:
    - Return all active questions with their related answers
    - Include answer details (id, text, point, career_option)
    - Be accessible publicly (AllowAny)
    - Return the expected response structure { "results": [...] }
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("question-list")

        # Create questions
        cls.q1 = Question.objects.create(title="What is Python?", is_active=True)
        cls.q2 = Question.objects.create(title="What is Django?", is_active=True)
        cls.q3 = Question.objects.create(title="Inactive Question", is_active=False)

        # Create career options
        cls.career1 = CareerOption.objects.create(title="Software Developer")
        cls.career2 = CareerOption.objects.create(title="Web Developer")

        # Add answers
        AnswerChoice.objects.create(
            question=cls.q1,
            text="A programming language",
            point=100,
            career_option=cls.career1,
        )
        AnswerChoice.objects.create(
            question=cls.q1,
            text="A type of snake",
            point=0,
            career_option=cls.career2,
        )
        AnswerChoice.objects.create(
            question=cls.q2,
            text="A web framework",
            point=80,
            career_option=cls.career1,
        )

    def test_list_questions_successfully(self):
        """
        API should return all active questions with their answers.
        """
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "data" in data
        results = data["data"]["results"]

        # Only active questions should be returned
        titles = [q["title"] for q in results]
        assert "Inactive Question" not in titles
        assert set(titles) == {"What is Python?", "What is Django?"}

        # Ensure answers are included and have correct fields
        for q in results:
            assert "answers" in q
            for ans in q["answers"]:
                assert "id" in ans
                assert "text" in ans

    def test_response_structure(self):
        """
        Each question must include id, title, and answers.
        """
        response = self.client.get(self.url)
        results = response.json()["data"]["results"]

        for q in results:
            assert "id" in q
            assert "title" in q
            assert "answers" in q

    def test_empty_list(self):
        """
        API should return an empty list if no questions exist.
        """
        Question.objects.all().delete()
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["results"] == []


class CalculateQuizResultAPITests(APITestCase):
    """
    Test suite for the Calculate Quiz Result API.

    This endpoint should:
    - Require authentication (Candidate only)
    - Return 400 if responses are missing or invalid
    - Calculate scores correctly for valid responses
    - Save QuizResult with top 3 careers
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("response-list")

        # Candidate user
        cls.candidate_user = Candidate.objects.create_user(
            email="candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )

        # Career options
        cls.career1 = CareerOption.objects.create(title="Backend Developer")
        cls.career2 = CareerOption.objects.create(title="Frontend Developer")

        cls.domain = Domain.objects.create(
            name="Engineering",
            description="Engineering domain",
        )

        cls.quiz_type = QuizType.objects.create(
            name="Career Quiz",
            description="Career guidance quiz",
            is_active=True,
        )
        cls.quiz = Quiz.objects.create(
            name="Main Career Quiz",
            quiz_type=cls.quiz_type,
            is_active=True,
        )

        # Questions
        cls.q1 = Question.objects.create(
            quiz=cls.quiz,
            title="What is Python?",
            is_active=True,
        )
        cls.q2 = Question.objects.create(
            quiz=cls.quiz,
            title="What is React?",
            is_active=True,
        )

        # Answer choices
        cls.ans1_q1 = AnswerChoice.objects.create(
            question=cls.q1,
            text="A programming language",
            point=80,
            career_option=cls.career1,
        )
        cls.ans2_q1 = AnswerChoice.objects.create(
            question=cls.q1, text="A snake", point=0, career_option=cls.career2
        )
        cls.ans1_q2 = AnswerChoice.objects.create(
            question=cls.q2, text="A JS library", point=70, career_option=cls.career2
        )

    def authenticate(self):
        """Helper method to authenticate as candidate"""
        self.client.force_authenticate(user=self.candidate_user)

    def test_requires_authentication(self):
        """
        API is now AllowAny. Anonymous users without email get 400 (not 401).
        With empty responses the view returns 400 before the email check.
        """
        response = self.client.post(
            self.url,
            {"quiz_id": self.quiz.id, "responses": []},
            format="json",
        )
        # AllowAny: anonymous requests proceed to view logic; empty responses → 400
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_responses(self):
        """
        API should return 400 if responses are missing.
        """
        self.authenticate()
        response = self.client.post(
            self.url,
            {"quiz_id": self.quiz.id, "responses": []},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_invalid_answer_ids(self):
        """
        API should return 400 if invalid answer IDs are given.
        """
        self.authenticate()
        payload = {
            "quiz_id": self.quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer": [99999]}  # invalid numeric ID
            ]
        }
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_calculates_results_with_career_option_ids_and_persists_domain(self):
        """
        API should include career option IDs in results and persist the selected domain.
        """
        self.authenticate()
        payload = {
            "quiz_id": self.quiz.id,
            "domain_id": self.domain.id,
            "responses": [
                {"question_id": self.q1.id, "answer": [self.ans1_q1.id]},
                {"question_id": self.q2.id, "answer": [self.ans1_q2.id]},
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        results = response.json()["data"]["results"]
        assert results[0]["id"] == self.career1.id
        quiz_result = self.candidate_user.quiz_results.latest("created_at")
        assert quiz_result.domain == self.domain

    def test_rejects_non_numeric_domain_id(self):
        """
        API should return 400 when domain_id is not numeric.
        """
        self.authenticate()
        payload = {
            "quiz_id": self.quiz.id,
            "domain_id": "invalid",
            "responses": [
                {"question_id": self.q1.id, "answer": [self.ans1_q1.id]},
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_rejects_answer_that_does_not_belong_to_question(self):
        self.authenticate()
        payload = {
            "quiz_id": self.quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer": [self.ans1_q2.id]},
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_handles_zero_score_answers_without_crashing(self):
        self.authenticate()
        payload = {
            "quiz_id": self.quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer": [self.ans2_q1.id]},
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        results = response.json()["data"]["results"]
        assert results[0]["score"] == 0
        assert results[0]["percentage"] == "75%"


class DetermineDomainAPITests(APITestCase):
    """
    Test suite for the Determine Domain API.

    This endpoint should:
    - Accept quiz_id and responses with question_id and answer_id
    - Calculate domain scores based on answer->domain mappings
    - Return the determined domain with questions from that domain's quiz types
    - Be accessible publicly (AllowAny)
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("determine-domain")

        # Create domains
        cls.domain_it = Domain.objects.create(
            name="IT",
            description="Information Technology"
        )
        cls.domain_healthcare = Domain.objects.create(
            name="Healthcare",
            description="Medical and Healthcare Industry"
        )

        # Create quiz types
        cls.quiz_type_discovery = QuizType.objects.create(
            name="Domain Discovery",
            description="Quiz to determine candidate's preferred domain",
            is_active=True,
        )
        cls.quiz_type_it = QuizType.objects.create(
            name="IT Career Quiz",
            description="IT-specific career quiz",
            is_active=True,
        )
        cls.quiz_type_it.domains.add(cls.domain_it)
        cls.quiz_type_healthcare = QuizType.objects.create(
            name="Healthcare Career Quiz",
            description="Healthcare-specific career quiz",
            is_active=True,
        )
        cls.quiz_type_healthcare.domains.add(cls.domain_healthcare)

        # Create domain discovery quiz
        cls.discovery_quiz = Quiz.objects.create(
            name="Domain Discovery Quiz",
            quiz_type=cls.quiz_type_discovery,
            is_active=True
        )

        # Create IT and Healthcare quizzes
        cls.it_quiz = Quiz.objects.create(
            name="IT Career Quiz",
            quiz_type=cls.quiz_type_it,
            is_active=True
        )
        cls.healthcare_quiz = Quiz.objects.create(
            name="Healthcare Career Quiz",
            quiz_type=cls.quiz_type_healthcare,
            is_active=True
        )

        # Create domain discovery questions
        cls.q1 = Question.objects.create(
            quiz=cls.discovery_quiz,
            title="Which activity do you prefer?",
            is_active=True
        )
        cls.q2 = Question.objects.create(
            quiz=cls.discovery_quiz,
            title="What interests you more?",
            is_active=True
        )

        # Create IT-specific questions (for results)
        cls.it_q1 = Question.objects.create(
            quiz=cls.it_quiz,
            title="What programming language interests you?",
            is_active=True
        )

        # Create Healthcare-specific questions (for results)
        cls.healthcare_q1 = Question.objects.create(
            quiz=cls.healthcare_quiz,
            title="Which healthcare specialty interests you?",
            is_active=True
        )

        # Create career options
        cls.career_dev = CareerOption.objects.create(title="Software Developer")
        cls.career_nurse = CareerOption.objects.create(title="Nurse")

        # Create answers with domain mappings for discovery quiz
        cls.ans1_q1_it = AnswerChoice.objects.create(
            question=cls.q1,
            text="Programming and building software",
            point=10,
            career_option=cls.career_dev
        )
        cls.ans1_q1_it.domains.add(cls.domain_it)

        cls.ans2_q1_healthcare = AnswerChoice.objects.create(
            question=cls.q1,
            text="Helping patients and caregiving",
            point=10,
            career_option=cls.career_nurse
        )
        cls.ans2_q1_healthcare.domains.add(cls.domain_healthcare)

        cls.ans1_q2_it = AnswerChoice.objects.create(
            question=cls.q2,
            text="Technology and innovation",
            point=15,
            career_option=cls.career_dev
        )
        cls.ans1_q2_it.domains.add(cls.domain_it)

        cls.ans2_q2_healthcare = AnswerChoice.objects.create(
            question=cls.q2,
            text="Healthcare and medicine",
            point=15,
            career_option=cls.career_nurse
        )
        cls.ans2_q2_healthcare.domains.add(cls.domain_healthcare)

        # Create answers for IT quiz
        AnswerChoice.objects.create(
            question=cls.it_q1,
            text="Python",
            point=10,
            career_option=cls.career_dev
        )

        # Create answers for Healthcare quiz
        AnswerChoice.objects.create(
            question=cls.healthcare_q1,
            text="Pediatrics",
            point=10,
            career_option=cls.career_nurse
        )

    def test_determine_domain_successfully(self):
        """
        API should determine domain based on answers and return domain-specific questions.
        """
        payload = {
            "quiz_id": self.discovery_quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer_id": self.ans1_q1_it.id},
                {"question_id": self.q2.id, "answer_id": self.ans1_q2_it.id},
            ]
        }
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK

        resp = response.json()
        data = resp["data"]
        assert "determined_domain" in data
        assert "all_domain_scores" in data
        assert "quiz_id" in data
        assert "questions" in data

        # IT should be the determined domain (both answers point to IT)
        assert data["determined_domain"]["name"] == "IT"
        assert data["determined_domain"]["score"] == 25  # 10 + 15

        # Should have quiz_id (either single ID or list of IDs)
        assert data["quiz_id"] is not None
        # Since all questions come from IT quiz, it should be the IT quiz ID
        if isinstance(data["quiz_id"], list):
            assert self.it_quiz.id in data["quiz_id"]
        else:
            assert data["quiz_id"] == self.it_quiz.id

    def test_determine_domain_returns_correct_questions(self):
        """
        API should return questions from quiz types associated with the determined domain.
        """
        payload = {
            "quiz_id": self.discovery_quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer_id": self.ans1_q1_it.id},
                {"question_id": self.q2.id, "answer_id": self.ans1_q2_it.id},
            ]
        }
        response = self.client.post(self.url, payload, format="json")
        data = response.json()["data"]

        # Should have IT-related questions
        question_titles = [q["title"] for q in data["questions"]]
        assert "What programming language interests you?" in question_titles
        # Should NOT have Healthcare questions
        assert "Which healthcare specialty interests you?" not in question_titles

        # Should have quiz_id in the response
        assert "quiz_id" in data
        assert data["quiz_id"] is not None

    def test_missing_quiz_id(self):
        """
        API should return 400 if quiz_id is missing.
        """
        payload = {
            "responses": [
                {"question_id": self.q1.id, "answer_id": self.ans1_q1_it.id}
            ]
        }
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_missing_responses(self):
        """
        API should return 400 if responses are missing.
        """
        payload = {
            "quiz_id": self.discovery_quiz.id,
            "responses": []
        }
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_invalid_quiz_id(self):
        """
        API should return 404 if quiz doesn't exist.
        """
        payload = {
            "quiz_id": 99999,
            "responses": [
                {"question_id": self.q1.id, "answer_id": self.ans1_q1_it.id}
            ]
        }
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_all_domain_scores_included(self):
        """
        API should return scores for all domains that received points.
        """
        payload = {
            "quiz_id": self.discovery_quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer_id": self.ans1_q1_it.id},  # IT: 10
                {"question_id": self.q2.id, "answer_id": self.ans2_q2_healthcare.id},  # Healthcare: 15
            ]
        }
        response = self.client.post(self.url, payload, format="json")
        data = response.json()["data"]

        # Should have both IT and Healthcare scores
        domain_names = [s["domain_name"] for s in data["all_domain_scores"]]
        assert "IT" in domain_names
        assert "Healthcare" in domain_names

        # Healthcare should be determined (15 > 10)
        assert data["determined_domain"]["name"] == "Healthcare"

    def test_rejects_answer_that_does_not_belong_to_question(self):
        payload = {
            "quiz_id": self.discovery_quiz.id,
            "responses": [
                {"question_id": self.q1.id, "answer_id": self.ans1_q2_it.id},
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()


class AnonymousQuizFlowTests(APITestCase):
    """
    Tests for the anonymous quiz submission flow.

    Three cases based on email state:
    - Case 1 (create_profile): brand-new email → candidate auto-created, quiz-result email sent
    - Case 2 (register): existing email without CandidateProfile → set-password email, Redis cached
    - Case 3 (login): existing email with CandidateProfile → inline results + login email, Redis cached
    """

    @classmethod
    def setUpTestData(cls):
        cls.url = reverse("response-list")

        cls.career1 = CareerOption.objects.create(
            title="Anon Backend Dev",
            title_en="Anon Backend Developer",
        )
        cls.domain = Domain.objects.create(name="AnonTech", description="Tech")
        cls.quiz_type = QuizType.objects.create(
            name="Anon Career Quiz", is_active=True
        )
        cls.quiz = Quiz.objects.create(
            name="Anon Main Quiz", quiz_type=cls.quiz_type, is_active=True
        )
        cls.q1 = Question.objects.create(
            quiz=cls.quiz, title="What do you enjoy?", is_active=True
        )
        cls.ans1 = AnswerChoice.objects.create(
            question=cls.q1, text="Building things", point=80, career_option=cls.career1
        )

    def _valid_payload(self, email=None):
        payload = {
            "quiz_id": self.quiz.id,
            "responses": [{"question_id": self.q1.id, "answer": [self.ans1.id]}],
        }
        if email is not None:
            payload["email"] = email
        return payload

    # ── Input validation ────────────────────────────────────────────────────

    def test_anonymous_without_email_returns_400(self):
        """Anonymous request with no email field → 400."""
        response = self.client.post(self.url, self._valid_payload(), format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()

    def test_anonymous_with_empty_email_returns_400(self):
        """Anonymous request with blank email → 400."""
        response = self.client.post(
            self.url, self._valid_payload(email=""), format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_anonymous_with_invalid_email_returns_400(self):
        """Anonymous request with malformed email → 400."""
        response = self.client.post(
            self.url, self._valid_payload(email="not-an-email"), format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ── Case 1: brand-new email ─────────────────────────────────────────────

    @patch("apps.quiz.services.email_service.send_email_from_template_type")
    def test_case1_new_email_creates_candidate_and_returns_create_profile(
        self, mock_send
    ):
        """Brand-new email: candidate auto-created, status=create_profile, email queued."""
        new_email = "brand_new_anon@example.com"
        response = self.client.post(
            self.url, self._valid_payload(email=new_email), format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["status"] == "create_profile"
        # Career cards must NOT be in the response body
        assert "results" not in data["data"]
        # Candidate was auto-created
        candidate = Candidate.objects.filter(email=new_email).first()
        assert candidate is not None
        assert candidate.is_candidate is True
        # QuizResult linked to candidate
        assert QuizResult.objects.filter(candidate=candidate).exists()
        # Email queued
        assert mock_send.called

    @patch("apps.quiz.services.email_service.send_email_from_template_type")
    def test_case1_saves_preferred_language_from_header(self, mock_send):
        """preferred_language is saved from Accept-Language header on auto-created candidate."""
        new_email = "lang_test_anon@example.com"
        self.client.post(
            self.url,
            self._valid_payload(email=new_email),
            format="json",
            HTTP_ACCEPT_LANGUAGE="ru",
        )
        candidate = Candidate.objects.filter(email=new_email).first()
        assert candidate is not None
        assert candidate.preferred_language == "ru"

    @patch("apps.quiz.services.email_service.send_email_from_template_type")
    def test_case1_email_sent_with_quiz_result_template(self, mock_send):
        """Case 1 must send an email using template_type=quiz-result."""
        new_email = "quiz_result_template@example.com"
        self.client.post(
            self.url, self._valid_payload(email=new_email), format="json"
        )
        assert mock_send.called
        call_kwargs = mock_send.call_args
        template_type = (
            call_kwargs.kwargs.get("template_type")
            or (call_kwargs.args[1] if len(call_kwargs.args) > 1 else None)
        )
        assert template_type == "quiz-result"

    # ── Case 2: existing email, no CandidateProfile ─────────────────────────

    @patch("apps.quiz.views.calculate_quiz._send_set_password_email")
    @patch("apps.quiz.services.pending_quiz_service.store_pending")
    def test_case2_existing_candidate_no_profile_returns_register(
        self, mock_store, mock_set_password
    ):
        """Existing email without CandidateProfile: status=register, QuizResult candidate=None, Redis cached."""
        Candidate.objects.create_user(
            email="no_profile@example.com",
            password="somepass",
            is_candidate=True,
        )
        response = self.client.post(
            self.url,
            self._valid_payload(email="no_profile@example.com"),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["status"] == "register"
        # Results must NOT be returned inline
        assert "results" not in data["data"]
        # QuizResult must have candidate=None
        result = (
            QuizResult.objects.filter(candidate__isnull=True)
            .order_by("-created_at")
            .first()
        )
        assert result is not None
        # Redis store was called
        assert mock_store.called
        # Set-password email was sent
        assert mock_set_password.called

    # ── Case 3: existing email with CandidateProfile ────────────────────────

    @patch("apps.quiz.services.pending_quiz_service.store_pending")
    def test_case3_existing_candidate_with_profile_returns_login_and_inline_results(
        self, mock_store
    ):
        """Existing email with CandidateProfile: status=login, inline results returned, Redis cached, no email sent."""
        candidate = Candidate.objects.create_user(
            email="with_profile@example.com",
            password="somepass",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=candidate,
            full_name="Test User",
        )
        response = self.client.post(
            self.url,
            self._valid_payload(email="with_profile@example.com"),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["status"] == "login"
        # Inline results returned for case 3
        assert "results" in data["data"]
        assert isinstance(data["data"]["results"], list)
        # Response message must mention logging in
        assert data["message"] is not None
        # QuizResult must have candidate=None
        result = (
            QuizResult.objects.filter(candidate__isnull=True)
            .order_by("-created_at")
            .first()
        )
        assert result is not None
        # Redis store was called (for deferred attachment on login)
        assert mock_store.called

    # ── Authenticated flow still works ──────────────────────────────────────

    def test_authenticated_candidate_still_gets_inline_results(self):
        """Authenticated candidates bypass anonymous flow and get inline results."""
        candidate = Candidate.objects.create_user(
            email="auth_candidate@example.com",
            password="testpass",
            is_candidate=True,
        )
        self.client.force_authenticate(user=candidate)
        response = self.client.post(
            self.url, self._valid_payload(), format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data["data"]

    # ── attach_pending_to_candidate ─────────────────────────────────────────

    def test_attach_pending_to_candidate_links_result(self):
        """attach_pending_to_candidate should link a null-candidate QuizResult to the candidate."""
        from apps.quiz.services.pending_quiz_service import (
            store_pending,
            attach_pending_to_candidate,
        )

        candidate = Candidate.objects.create_user(
            email="attach_test@example.com",
            password="pass",
            is_candidate=True,
        )
        result = QuizResult.objects.create(
            candidate=None,
            quiz=self.quiz,
            career_options=[],
            domain=self.domain,
        )
        store_pending(candidate.email, str(result.id))
        attached = attach_pending_to_candidate(candidate)
        assert attached is True
        result.refresh_from_db()
        assert result.candidate == candidate
