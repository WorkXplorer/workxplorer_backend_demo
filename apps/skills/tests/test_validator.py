import json
from unittest.mock import patch

from django.test import TestCase

from apps.authentication.models import Candidate
from apps.resumes.models import Resume, ResumeSkill
from apps.skills.models import Skill
from apps.ai.services.skill_validator import validate_passive_skills


class FakeAIClient:
    """Minimal stand-in for GroqClient used by the validator."""

    def __init__(self, skills_result):
        self._skills_result = skills_result

    def cached_completion(self, messages, cache_prefix, prompt, json_mode=False):
        return {
            "choices": [
                {"message": {"content": json.dumps({"skills": self._skills_result})}}
            ]
        }

    def parse_json_response(self, content):
        return json.loads(content)


class SkillValidatorTests(TestCase):
    def test_rejected_skill_is_deleted(self):
        skill = Skill.objects.create(name="asdqwe gibberish", is_active=False)
        client = FakeAIClient(
            [
                {
                    "skill_id": skill.id,
                    "approved": False,
                    "duplicate_of_skill_id": None,
                    "reason": "Not a real skill",
                }
            ]
        )

        result = validate_passive_skills(client)

        self.assertEqual(result["rejected"], 1)
        self.assertFalse(Skill.objects.filter(id=skill.id).exists())

    def test_approved_skill_is_activated_and_translated(self):
        skill = Skill.objects.create(name="Rust", is_active=False)
        client = FakeAIClient(
            [
                {
                    "skill_id": skill.id,
                    "approved": True,
                    "duplicate_of_skill_id": None,
                    "name_en": "Rust",
                    "name_ru": "Раст",
                    "name_uz": "Rust",
                    "description_en": "A systems programming language.",
                    "description_ru": "Системный язык программирования.",
                    "description_uz": "Tizim dasturlash tili.",
                    "reason": "Valid skill",
                }
            ]
        )

        result = validate_passive_skills(client)

        self.assertEqual(result["approved"], 1)
        skill.refresh_from_db()
        self.assertTrue(skill.is_active)
        self.assertEqual(skill.name_ru, "Раст")
        self.assertEqual(skill.name_uz, "Rust")

    def test_duplicate_skill_is_deleted_and_resume_repointed(self):
        canonical = Skill.objects.create(name="JavaScript", is_active=True)
        duplicate = Skill.objects.create(name="JS", is_active=False)

        candidate = Candidate.objects.create_user(
            email="dup-candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )
        resume = Resume.objects.create(candidate=candidate, description="x")
        ResumeSkill.objects.create(resume=resume, skill=duplicate)

        client = FakeAIClient(
            [
                {
                    "skill_id": duplicate.id,
                    "approved": True,
                    "duplicate_of_skill_id": canonical.id,
                    "reason": "Same as JavaScript",
                }
            ]
        )

        result = validate_passive_skills(client)

        self.assertEqual(result["duplicates"], 1)
        self.assertFalse(Skill.objects.filter(id=duplicate.id).exists())
        # The candidate keeps the skill — now pointing at the canonical one.
        resume_skill = ResumeSkill.objects.get(resume=resume)
        self.assertEqual(resume_skill.skill_id, canonical.id)

    def test_pending_duplicate_of_pending_skill_merges_when_canonical_listed_first(self):
        """
        Two candidates independently submit the same still-pending skill.
        The AI approves one and flags the other as its duplicate. Processing
        is order-independent (approvals run in a first pass, duplicates in a
        second), so this holds regardless of which order the AI listed the
        two entries in — see the sibling test below for the reversed order.
        """
        canonical = Skill.objects.create(name="Golang", is_active=False)
        duplicate = Skill.objects.create(name="Go lang", is_active=False)

        candidate = Candidate.objects.create_user(
            email="pending-dup-candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )
        resume = Resume.objects.create(candidate=candidate, description="x")
        ResumeSkill.objects.create(resume=resume, skill=duplicate)

        client = FakeAIClient(
            [
                {
                    "skill_id": canonical.id,
                    "approved": True,
                    "duplicate_of_skill_id": None,
                    "name_en": "Go",
                    "name_ru": "Go",
                    "name_uz": "Go",
                    "description_en": "A language.",
                    "description_ru": "Язык.",
                    "description_uz": "Til.",
                    "reason": "Valid skill",
                },
                {
                    "skill_id": duplicate.id,
                    "approved": True,
                    "duplicate_of_skill_id": canonical.id,
                    "reason": "Same as Golang",
                },
            ]
        )

        result = validate_passive_skills(client)

        self.assertEqual(result["approved"], 1)
        self.assertEqual(result["duplicates"], 1)
        canonical.refresh_from_db()
        self.assertTrue(canonical.is_active)
        self.assertFalse(Skill.objects.filter(id=duplicate.id).exists())
        # Re-pointed to the canonical, not lost.
        resume_skill = ResumeSkill.objects.get(resume=resume)
        self.assertEqual(resume_skill.skill_id, canonical.id)

    def test_pending_duplicate_of_pending_skill_merges_when_duplicate_listed_first(self):
        """
        Same scenario as above, but the AI lists the duplicate entry before
        its (still-pending) canonical. Prior to the two-pass fix, this
        ordering hit the delete-only path in ``_remove_duplicate_skill``
        (canonical not yet ``is_active``), hard-deleting the duplicate and
        cascade-dropping the candidate's resume skill instead of re-pointing
        it. Approvals now always run before duplicate merges, so this must
        behave identically to the canonical-first ordering.
        """
        canonical = Skill.objects.create(name="Golang", is_active=False)
        duplicate = Skill.objects.create(name="Go lang", is_active=False)

        candidate = Candidate.objects.create_user(
            email="pending-dup-candidate-reversed@test.com",
            password="testpass123",
            is_candidate=True,
        )
        resume = Resume.objects.create(candidate=candidate, description="x")
        ResumeSkill.objects.create(resume=resume, skill=duplicate)

        client = FakeAIClient(
            [
                {
                    "skill_id": duplicate.id,
                    "approved": True,
                    "duplicate_of_skill_id": canonical.id,
                    "reason": "Same as Golang",
                },
                {
                    "skill_id": canonical.id,
                    "approved": True,
                    "duplicate_of_skill_id": None,
                    "name_en": "Go",
                    "name_ru": "Go",
                    "name_uz": "Go",
                    "description_en": "A language.",
                    "description_ru": "Язык.",
                    "description_uz": "Til.",
                    "reason": "Valid skill",
                },
            ]
        )

        result = validate_passive_skills(client)

        self.assertEqual(result["approved"], 1)
        self.assertEqual(result["duplicates"], 1)
        canonical.refresh_from_db()
        self.assertTrue(canonical.is_active)
        self.assertFalse(Skill.objects.filter(id=duplicate.id).exists())
        # Re-pointed to the canonical, not lost — even though the duplicate
        # entry came first in the AI's response.
        resume_skill = ResumeSkill.objects.get(resume=resume)
        self.assertEqual(resume_skill.skill_id, canonical.id)


class ValidatePassiveSkillsTaskTests(TestCase):
    @patch("apps.ai.services.skill_validator.validate_passive_skills")
    def test_succeeds_via_groq(self, mock_validate):
        from apps.skills.tasks import validate_passive_skills_task

        mock_validate.side_effect = [
            {"message": "ok", "approved": 0, "rejected": 0, "duplicates": 0},
        ]

        result = validate_passive_skills_task()

        self.assertEqual(result["message"], "ok")
        self.assertEqual(mock_validate.call_count, 1)

    @patch("apps.ai.services.skill_validator.validate_passive_skills")
    def test_raises_when_provider_fails(self, mock_validate):
        from apps.skills.tasks import validate_passive_skills_task

        mock_validate.side_effect = RuntimeError("provider down")

        with self.assertRaises(RuntimeError):
            validate_passive_skills_task()
        self.assertEqual(mock_validate.call_count, 1)
