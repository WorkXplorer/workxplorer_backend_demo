from django.test import TestCase
from rest_framework import serializers

from apps.authentication.models import Candidate
from apps.resumes.models import Resume, ResumeSkill
from apps.resumes.serializers.resume import (
    MAX_RESUME_SKILLS,
    ResumeSerializer,
    ResumeSkillSerializer,
)
from apps.skills.models import Skill


class ResumeSkillWarningTests(TestCase):
    def setUp(self):
        self.candidate = Candidate.objects.create_user(
            email="resume-skill-warning@test.com",
            password="testpass123",
            is_candidate=True,
        )
        self.resume = Resume.objects.create(
            candidate=self.candidate, description="x"
        )

    def test_pending_skill_carries_a_warning(self):
        skill = Skill.objects.create(name="Pending Skill", is_active=False)
        resume_skill = ResumeSkill.objects.create(resume=self.resume, skill=skill)

        data = ResumeSkillSerializer(resume_skill).data

        self.assertTrue(data["is_pending"])
        self.assertIsNotNone(data["warning"])

    def test_approved_skill_has_no_warning(self):
        skill = Skill.objects.create(name="Approved Skill", is_active=True)
        resume_skill = ResumeSkill.objects.create(resume=self.resume, skill=skill)

        data = ResumeSkillSerializer(resume_skill).data

        self.assertFalse(data["is_pending"])
        self.assertIsNone(data["warning"])


class ResumeSkillLimitTests(TestCase):
    def test_rejects_more_than_max_skills(self):
        too_many = [{"skill_id": i} for i in range(MAX_RESUME_SKILLS + 1)]
        with self.assertRaises(serializers.ValidationError):
            ResumeSerializer().validate_skills_data(too_many)

    def test_allows_up_to_max_skills(self):
        skills = [
            Skill.objects.create(name=f"Skill {i}", is_active=True)
            for i in range(MAX_RESUME_SKILLS)
        ]
        payload = [{"skill_id": s.id} for s in skills]

        validated = ResumeSerializer().validate_skills_data(payload)

        self.assertEqual(len(validated), MAX_RESUME_SKILLS)
