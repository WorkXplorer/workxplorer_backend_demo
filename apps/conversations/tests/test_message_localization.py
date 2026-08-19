"""Tests for messages the platform writes rather than a person.

Two rules are under test here:

1. A platform-written message reads in the language of whoever is *looking*
   at it. It used to be rendered once, in the language of whoever triggered
   it, which meant a recruiter opening a chat with an Uzbek-speaking
   applicant read the platform's own sentences in Uzbek.
2. An AI auto-rejection carries the explanation the AI already wrote for the
   candidate — the same text the vacancy page shows them — so the chat does
   not just say "status changed" and leave both sides guessing.
"""

from django.test import TestCase
from django.utils import translation

from apps.authentication.models import Candidate, Recruiter, Company
from apps.profiles.models import CandidateProfile, RecruiterProfile
from apps.vacancies.models import Vacancy
from apps.applications.models import JobApplication

from ..models import Conversation, Message, MessageType
from ..serializers.conversations import MessageSerializer
from ..services import render_default_message, resolve_message_content


class PlatformMessageLanguageTests(TestCase):
    """The apply message follows the reader, not the applicant."""

    def setUp(self):
        self.company = Company.objects.create(name="Test Company", tin="123456789", is_active=True)
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123",
            is_recruiter=True, company=self.company,
        )
        RecruiterProfile.objects.create(recruiter=self.recruiter, full_name="Test Recruiter")
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123", is_candidate=True,
        )
        CandidateProfile.objects.create(candidate=self.candidate, full_name="Test Candidate")
        self.vacancy = Vacancy.objects.create(
            title="Стажёр BizDev", created_by=self.recruiter,
            company=self.company, is_active=True,
        )

    def _apply(self):
        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy, cover_letter="",
        )
        conversation = Conversation.objects.get(application=application)
        return conversation.messages.first()

    def test_apply_message_is_stored_with_a_key_not_final_text(self):
        message = self._apply()
        self.assertEqual(message.metadata.get("message_key"), "candidate_applied_to_vacancy")
        self.assertEqual(
            message.metadata.get("message_params"), {"vacancy_title": "Стажёр BizDev"}
        )

    def test_apply_message_renders_in_each_readers_language(self):
        message = self._apply()

        rendered = {}
        for language in ("ru", "uz", "en"):
            with translation.override(language):
                rendered[language] = resolve_message_content(message)

        # The vacancy title is the recruiter's own text and stays as written;
        # the sentence around it is what changes.
        for language, text in rendered.items():
            self.assertIn("Стажёр BizDev", text, f"{language} lost the vacancy title")

        self.assertEqual(len(set(rendered.values())), 3, rendered)
        self.assertIn("откликнулся", rendered["ru"])
        self.assertIn("murojaat", rendered["uz"])

    def test_message_a_person_typed_is_never_rewritten(self):
        conversation = Conversation.objects.get(application__candidate=self.candidate) \
            if Conversation.objects.filter(application__candidate=self.candidate).exists() \
            else None
        if conversation is None:
            self._apply()
            conversation = Conversation.objects.get(application__candidate=self.candidate)

        typed = Message.objects.create(
            conversation=conversation, sender_type="CANDIDATE",
            message_type=MessageType.TEXT, content="Salom, men murojaat qildim",
        )
        with translation.override("ru"):
            self.assertEqual(resolve_message_content(typed), "Salom, men murojaat qildim")

    def test_message_written_before_keys_existed_still_reads(self):
        self._apply()
        conversation = Conversation.objects.get(application__candidate=self.candidate)
        legacy = Message.objects.create(
            conversation=conversation, sender_type="CANDIDATE",
            message_type=MessageType.TEXT,
            content="Nomzod vakansiyaga murojaat qildi: Стажёр BizDev",
            metadata={},
        )
        with translation.override("ru"):
            self.assertEqual(
                resolve_message_content(legacy),
                "Nomzod vakansiyaga murojaat qildi: Стажёр BizDev",
            )

    def test_unknown_placeholder_falls_back_to_the_template(self):
        with translation.override("ru"):
            text = render_default_message("candidate_applied_to_vacancy", {"wrong": "x"})
        self.assertTrue(text)

    def test_unknown_key_renders_empty(self):
        self.assertEqual(render_default_message("no_such_key"), "")


class AIRejectionSummaryTests(TestCase):
    """The AI's own explanation rides along with the status change."""

    def setUp(self):
        self.company = Company.objects.create(name="Test Company", tin="987654321", is_active=True)
        self.recruiter = Recruiter.objects.create_user(
            email="rec2@test.com", password="testpass123",
            is_recruiter=True, company=self.company,
        )
        RecruiterProfile.objects.create(recruiter=self.recruiter, full_name="Rec Two")
        self.candidate = Candidate.objects.create_user(
            email="cand2@test.com", password="testpass123", is_candidate=True,
        )
        CandidateProfile.objects.create(candidate=self.candidate, full_name="Cand Two")
        self.vacancy = Vacancy.objects.create(
            title="Менеджер по продажам", created_by=self.recruiter,
            company=self.company, is_active=True,
        )
        self.application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy, cover_letter="hi",
        )
        self.conversation = Conversation.objects.get(application=self.application)

        self.message = Message.objects.create(
            conversation=self.conversation,
            sender_type="SYSTEM",
            message_type=MessageType.STATUS_CHANGE,
            content="",
            metadata={
                "old_status": "APPLIED",
                "new_status": "AI_FAILED",
                "old_status_display": "Applied",
                "new_status_display": "AI rejected",
                "recruiter_note": "",
                "changed_by": "SYSTEM",
                "changed_at": "2026-07-31T10:00:00+00:00",
            },
        )

    def _roadmap(self, summary):
        from apps.student_analytics.models import VacancySkillRoadmap

        VacancySkillRoadmap.objects.update_or_create(
            application=self.application, defaults={"rejection_summary": summary},
        )

    def _serialize(self):
        return MessageSerializer(self.message).data

    def test_summary_is_attached_in_the_readers_language(self):
        self._roadmap({
            "uz": "Afsuski, siz tanlanmadingiz.",
            "ru": "К сожалению, мы не смогли предложить вам позицию.",
            "en": "Unfortunately we could not offer you the position.",
        })

        for language, expected in (
            ("ru", "К сожалению, мы не смогли предложить вам позицию."),
            ("uz", "Afsuski, siz tanlanmadingiz."),
            ("en", "Unfortunately we could not offer you the position."),
        ):
            with translation.override(language):
                data = self._serialize()
            self.assertEqual(data["metadata"]["ai_rejection_summary"], expected)

    def test_both_sides_get_the_same_text(self):
        # One rendering, no audience gating: whatever the candidate is told is
        # what the recruiter sees.
        self._roadmap({"ru": "Одна и та же формулировка.", "uz": "", "en": ""})
        with translation.override("ru"):
            first = self._serialize()["metadata"]["ai_rejection_summary"]
            second = self._serialize()["metadata"]["ai_rejection_summary"]
        self.assertEqual(first, second)

    def test_missing_language_falls_back_to_english(self):
        self._roadmap({"uz": "", "ru": "", "en": "English fallback."})
        with translation.override("ru"):
            data = self._serialize()
        self.assertEqual(data["metadata"]["ai_rejection_summary"], "English fallback.")

    def test_nothing_is_attached_before_the_roadmap_job_finishes(self):
        # The summary is written by a background job that runs after this
        # message exists, so the field is simply absent until it lands.
        with translation.override("ru"):
            data = self._serialize()
        self.assertNotIn("ai_rejection_summary", data["metadata"])

    def test_recruiter_status_change_carries_no_summary(self):
        self._roadmap({"ru": "Не должно появиться здесь.", "uz": "", "en": ""})
        message = Message.objects.create(
            conversation=self.conversation,
            sender_type="RECRUITER",
            message_type=MessageType.STATUS_CHANGE,
            content="note",
            metadata={
                "old_status": "APPLIED", "new_status": "REJECTED",
                "changed_by": "RECRUITER", "recruiter_note": "note",
            },
        )
        with translation.override("ru"):
            data = MessageSerializer(message).data
        self.assertNotIn("ai_rejection_summary", data["metadata"])

    def test_a_summary_in_only_one_language_still_reaches_the_recruiter(self):
        # The generator blanks any language the model skipped. A recruiter
        # reading English must not be left with an unexplained rejection.
        self._roadmap({"uz": "", "ru": "Не хватает навыков ведения переговоров.", "en": ""})
        with translation.override("en"):
            data = self._serialize()
        self.assertEqual(
            data["metadata"]["ai_rejection_summary"],
            "Не хватает навыков ведения переговоров.",
        )

    def test_an_empty_summary_attaches_nothing(self):
        self._roadmap({"uz": "", "ru": "", "en": ""})
        with translation.override("ru"):
            data = self._serialize()
        self.assertNotIn("ai_rejection_summary", data["metadata"])

    def test_moving_back_to_applied_carries_no_summary(self):
        # AI revaluation returns an application to APPLIED. The roadmap from
        # the earlier rejection still exists, but that notice is about the
        # candidate being back in the running — it must not explain a
        # rejection that no longer stands.
        self._roadmap({"ru": "Причина прошлого отказа.", "uz": "", "en": ""})
        message = Message.objects.create(
            conversation=self.conversation,
            sender_type="SYSTEM",
            message_type=MessageType.STATUS_CHANGE,
            content="",
            metadata={
                "old_status": "AI_FAILED",
                "new_status": "APPLIED",
                "changed_by": "RECRUITER",
                "recruiter_note": "",
            },
        )
        with translation.override("ru"):
            data = MessageSerializer(message).data
        self.assertNotIn("ai_rejection_summary", data["metadata"])
