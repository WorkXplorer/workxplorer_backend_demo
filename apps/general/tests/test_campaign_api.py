from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate, Company, CustomUser, Recruiter
from apps.domain.models import Domain
from apps.edupartners.models import EduPartner, EduPartnersType
from apps.general.models import EmailTemplate
from apps.quiz.models import Quiz, QuizResult, QuizType
from apps.resumes.models import Resume
from apps.vacancies.models import Vacancy


class ManualEmailCampaignAPIViewTests(APITestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_superuser(
            email="admin@test.com",
            password="pass123",
        )
        self.client.force_authenticate(user=self.admin)
        self.url = reverse("manual-email-campaign-send")

        EmailTemplate.objects.create(
            template_type="vacancy-newsletter",
            name="vacancy-newsletter",
            language="uz",
            subject="Yangi vakansiyalar: {{ total_count }}",
            body=SimpleUploadedFile(
                "newsletter.html",
                b"<html>{% for vacancy in vacancies %}{{ vacancy.url }}{% endfor %}</html>",
                content_type="text/html",
            ),
        )

        self.tech = Domain.objects.create(name="IT")
        self.finance = Domain.objects.create(name="Finance")
        self.company = Company.objects.create(
            name="WorkXplorer",
            tin="123456789",
            domain=self.tech,
            is_active=True,
        )
        self.recruiter = Recruiter.objects.create_user(
            email="owner@test.com",
            password="pass123",
            company=self.company,
            is_active=True,
            is_recruiter=True,
        )

    def _candidate(self, email):
        return Candidate.objects.create_user(
            email=email,
            password="pass123",
            is_candidate=True,
            is_active=True,
        )

    def _vacancy(self, title, domain, is_active=True):
        return Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            domain=domain,
            title=title,
            about_us="About company",
            requirements="Python",
            responsibilities="Build APIs",
            is_active=is_active,
        )

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_candidate_campaign_uses_resume_and_quiz_domains(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        resume_candidate = self._candidate("resume@test.com")
        quiz_candidate = self._candidate("quiz@test.com")

        tech_vacancy = self._vacancy("Backend Developer", self.tech)
        finance_vacancy = self._vacancy("Credit Analyst", self.finance)
        self._vacancy("Inactive Developer", self.tech, is_active=False)

        Resume.objects.create(
            candidate=resume_candidate,
            title="Resume",
            description="Experienced developer",
            position="Backend Developer",
            domain=self.tech,
        )
        quiz_type = QuizType.objects.create(name="Career")
        quiz_type.domains.add(self.finance)
        quiz = Quiz.objects.create(name="Career Quiz", quiz_type=quiz_type)
        QuizResult.objects.create(
            candidate=quiz_candidate,
            quiz=quiz,
            domain=self.finance,
            career_options=[],
        )

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": [
                    "resume@test.com",
                    "quiz@test.com",
                    "missing@test.com",
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["audience"], "candidates")
        self.assertEqual(
            data["sent"],
            [
                {"email": "quiz@test.com", "delay_seconds": 0},
                {"email": "resume@test.com", "delay_seconds": 0},
            ],
        )
        self.assertEqual(data["skipped_count"], 1)
        self.assertEqual(mock_send.call_count, 2)

        contexts_by_email = {
            call.kwargs["to_email"]: call.kwargs["context"]
            for call in mock_send.call_args_list
        }
        self.assertEqual(
            [item["id"] for item in contexts_by_email["resume@test.com"]["vacancies"]],
            [str(tech_vacancy.id)],
        )
        self.assertEqual(
            [item["id"] for item in contexts_by_email["quiz@test.com"]["vacancies"]],
            [str(finance_vacancy.id)],
        )

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_recruiter_campaign_uses_company_domain(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        tech_vacancy = self._vacancy("Backend Developer", self.tech)
        self._vacancy("Credit Analyst", self.finance)

        response = self.client.post(
            self.url,
            {
                "audience": "recruiters",
                "template_type": "vacancy-newsletter",
                "emails": ["owner@test.com"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["audience"], "recruiters")
        self.assertEqual(data["sent"], [{"email": "owner@test.com", "delay_seconds": 0}])

        context = mock_send.call_args.kwargs["context"]
        self.assertEqual(context["recipient_type"], "recruiter")
        self.assertEqual(context["company"], "WorkXplorer")
        self.assertEqual(
            [item["id"] for item in context["vacancies"]],
            [str(tech_vacancy.id)],
        )

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_vacancy_limit_defaults_to_five_and_allows_seven(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        candidate = self._candidate("limit@test.com")
        Resume.objects.create(
            candidate=candidate,
            title="Limit Resume",
            description="Limit recipient",
            position="Developer",
            domain=self.tech,
        )
        for index in range(8):
            self._vacancy(f"Tech Vacancy {index}", self.tech)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["limit@test.com"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertEqual(len(mock_send.call_args.kwargs["context"]["vacancies"]), 5)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["limit@test.com"],
                "vacancy_limit": 7,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertEqual(len(mock_send.call_args.kwargs["context"]["vacancies"]), 7)

    def test_vacancy_limit_rejects_more_than_seven(self):
        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["limit@test.com"],
                "vacancy_limit": 8,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vacancy_limit", str(response.json()))

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_candidate_without_domain_gets_default_vacancies(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        self._candidate("nodomain@test.com")
        default_vacancy = self._vacancy("Default Vacancy", self.tech)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["nodomain@test.com"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["sent"], [{"email": "nodomain@test.com", "delay_seconds": 0}])
        self.assertEqual(data["skipped_count"], 0)

        context = mock_send.call_args.kwargs["context"]
        self.assertEqual(
            [item["id"] for item in context["vacancies"]],
            [str(default_vacancy.id)],
        )

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_default_vacancies_prefer_most_recently_created(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        self._candidate("nodomain-recency@test.com")

        older = self._vacancy("Older Vacancy", self.tech)
        newer = self._vacancy("Newer Vacancy", self.finance)
        Vacancy.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=2))
        Vacancy.objects.filter(pk=newer.pk).update(created_at=timezone.now() - timedelta(days=1))

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["nodomain-recency@test.com"],
                "vacancy_limit": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        context = mock_send.call_args.kwargs["context"]
        self.assertEqual(
            [item["id"] for item in context["vacancies"]],
            [str(newer.id), str(older.id)],
        )

    @staticmethod
    def _embedding(active_index):
        vector = [0.0] * 384
        vector[active_index] = 1.0
        return vector

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_embedded_resume_uses_similarity_with_recency_tiebreak(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        candidate = self._candidate("embedded@test.com")
        Resume.objects.create(
            candidate=candidate,
            title="Resume",
            description="Backend developer",
            position="Backend Developer",
            is_embedded=True,
            embedding=self._embedding(0),
        )

        # Two vacancies with identical (perfect-match) embeddings: recency
        # should break the tie. A third, orthogonal-embedding vacancy is
        # below the similarity threshold and must not be recommended.
        older_match = self._vacancy("Older Perfect Match", self.tech)
        newer_match = self._vacancy("Newer Perfect Match", self.tech)
        unrelated = self._vacancy("Unrelated Vacancy", self.tech)
        Vacancy.objects.filter(pk=older_match.pk).update(
            is_embedded=True, embedding=self._embedding(0), created_at=timezone.now() - timedelta(days=2)
        )
        Vacancy.objects.filter(pk=newer_match.pk).update(
            is_embedded=True, embedding=self._embedding(0), created_at=timezone.now() - timedelta(days=1)
        )
        Vacancy.objects.filter(pk=unrelated.pk).update(
            is_embedded=True, embedding=self._embedding(1)
        )

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["embedded@test.com"],
                "vacancy_limit": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        context = mock_send.call_args.kwargs["context"]
        self.assertEqual(
            [item["id"] for item in context["vacancies"]],
            [str(newer_match.id), str(older_match.id)],
        )

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_candidate_without_matching_vacancy_is_skipped(self, mock_send):
        candidate = self._candidate("novacancy@test.com")
        Resume.objects.create(
            candidate=candidate,
            title="Finance Resume",
            description="Finance recipient",
            position="Analyst",
            domain=self.finance,
        )
        self._vacancy("Inactive Finance", self.finance, is_active=False)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["novacancy@test.com"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["recipient_count"], 1)
        self.assertEqual(data["sent_count"], 0)
        self.assertEqual(data["skipped_count"], 1)
        mock_send.assert_not_called()

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_edupartner_ids_selects_all_active_candidates_at_that_university(
        self, mock_send
    ):
        mock_send.return_value = MagicMock(id="rq-job")
        edupartner_type = EduPartnersType.objects.create(name="University")
        msu = EduPartner.objects.create(
            name="Lomonosov Moscow State University branch in Tashkent (MSU-TB)",
            edupartner_type=edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
        )
        other = EduPartner.objects.create(
            name="Tashkent State University of Economics (TSUE)",
            edupartner_type=edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
        )

        msu_candidate = self._candidate("msu@test.com")
        msu_candidate.edupartner = msu
        msu_candidate.save(update_fields=["edupartner"])

        other_candidate = self._candidate("tsue@test.com")
        other_candidate.edupartner = other
        other_candidate.save(update_fields=["edupartner"])

        inactive_msu_candidate = self._candidate("inactive-msu@test.com")
        inactive_msu_candidate.edupartner = msu
        inactive_msu_candidate.is_active = False
        inactive_msu_candidate.save(update_fields=["edupartner", "is_active"])

        self._vacancy("Backend Developer", self.tech)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "edupartner_ids": [str(msu.id)],
                "language": "ru",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["recipient_count"], 1)
        self.assertEqual(data["sent"], [{"email": "msu@test.com", "delay_seconds": 0}])
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["language"], "ru")

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_no_university_only_selects_candidates_without_edupartner(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        edupartner_type = EduPartnersType.objects.create(name="University")
        msu = EduPartner.objects.create(
            name="Lomonosov Moscow State University branch in Tashkent (MSU-TB)",
            edupartner_type=edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
        )
        self._vacancy("Backend Developer", self.tech)

        with_uni = self._candidate("with-uni@test.com")
        with_uni.edupartner = msu
        with_uni.save(update_fields=["edupartner"])

        without_uni = self._candidate("no-uni@test.com")
        inactive_without_uni = self._candidate("inactive-no-uni@test.com")
        inactive_without_uni.is_active = False
        inactive_without_uni.save(update_fields=["is_active"])

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "no_university_only": True,
                "language": "uz",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["recipient_count"], 1)
        self.assertEqual(data["sent"], [{"email": "no-uni@test.com", "delay_seconds": 0}])

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_no_selector_targets_full_active_base_and_recipient_limit_caps_it(
        self, mock_send
    ):
        mock_send.return_value = MagicMock(id="rq-job")
        self._vacancy("Backend Developer", self.tech)
        self._candidate("alice@test.com")
        self._candidate("bob@test.com")
        carol = self._candidate("carol@test.com")
        carol.is_active = False
        carol.save(update_fields=["is_active"])

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "recipient_limit": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(data["recipient_limit"], 1)
        self.assertEqual(data["recipient_count"], 1)
        self.assertEqual(data["sent"], [{"email": "alice@test.com", "delay_seconds": 0}])

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_cooldown_seconds_paces_delay_between_successive_sends(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        self._vacancy("Backend Developer", self.tech)
        self._candidate("alice@test.com")
        self._candidate("bob@test.com")
        self._candidate("carol@test.com")

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "cooldown_seconds": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertEqual(
            data["sent"],
            [
                {"email": "alice@test.com", "delay_seconds": 0},
                {"email": "bob@test.com", "delay_seconds": 30},
                {"email": "carol@test.com", "delay_seconds": 60},
            ],
        )
        delays = [call.kwargs["delay_seconds"] for call in mock_send.call_args_list]
        self.assertEqual(delays, [0, 30, 60])

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_preferred_language_controls_template_language_and_urls(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        EmailTemplate.objects.create(
            template_type="vacancy-newsletter",
            name="vacancy-newsletter-ru",
            language="ru",
            subject="Новые вакансии: {{ total_count }}",
            body=SimpleUploadedFile(
                "newsletter-ru.html",
                b"<html>{{ vacancy_url }}</html>",
                content_type="text/html",
            ),
        )
        candidate = self._candidate("ru@test.com")
        candidate.preferred_language = "ru"
        candidate.save(update_fields=["preferred_language"])
        Resume.objects.create(
            candidate=candidate,
            title="RU Resume",
            description="RU recipient",
            position="Developer",
            domain=self.tech,
        )
        vacancy = self._vacancy("Backend Developer", self.tech)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["ru@test.com"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs["language"], "ru")
        frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
        self.assertEqual(
            call_kwargs["context"]["vacancy_url"],
            f"{frontend_url}/ru/dashboard/vacancies/{vacancy.id}",
        )

    @patch("apps.general.services.campaign_email_service.send_email_from_template_type")
    def test_campaign_language_override_controls_template_language_and_urls(self, mock_send):
        mock_send.return_value = MagicMock(id="rq-job")
        EmailTemplate.objects.create(
            template_type="vacancy-newsletter",
            name="vacancy-newsletter-ru",
            language="ru",
            subject="Новые вакансии: {{ total_count }}",
            body=SimpleUploadedFile(
                "newsletter-ru.html",
                b"<html>{{ vacancy_url }}</html>",
                content_type="text/html",
            ),
        )
        candidate = self._candidate("override@test.com")
        candidate.preferred_language = "uz"
        candidate.save(update_fields=["preferred_language"])
        Resume.objects.create(
            candidate=candidate,
            title="UZ Resume",
            description="UZ recipient",
            position="Developer",
            domain=self.tech,
        )
        vacancy = self._vacancy("Backend Developer", self.tech)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["override@test.com"],
                "language": "ru",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs["language"], "ru")
        self.assertEqual(call_kwargs["context"]["language"], "ru")
        frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
        self.assertEqual(
            call_kwargs["context"]["vacancy_url"],
            f"{frontend_url}/ru/dashboard/vacancies/{vacancy.id}",
        )

    def test_language_rejects_unsupported_value(self):
        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["candidate@test.com"],
                "language": "de",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("language", str(response.json()))

    def test_language_validation_error_is_translated(self):
        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["candidate@test.com"],
                "language": "sss",
            },
            format="json",
            HTTP_ACCEPT_LANGUAGE="uz",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["error"]["field_errors"]["language"][0],
            "Qo‘llab-quvvatlanmaydigan til. Ruxsat etilgan qiymatlar: uz, ru, en.",
        )

    def test_require_template_type(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template_type", str(response.json()))

    def test_require_admin_user(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.url,
            {
                "template_type": "vacancy-newsletter",
                "emails": ["candidate@test.com"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
