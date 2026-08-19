from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.general.models import DomainMarketSkill
from apps.authentication.models import Candidate
from apps.domain.models import Domain
from apps.resumes.models import Resume, ResumeSkill
from apps.skills.models import Skill
from apps.general.services import hh_aliases


class HHAliasesTests(APITestCase):
    def test_vacancy_title_matches_smm_cyrillic_alias(self):
        self.assertTrue(
            hh_aliases.vacancy_title_matches_query(
                {"title": "СММ специалист"}, "SMM-менеджер"
            )
        )

    def test_vacancy_title_matches_market_aliases(self):
        self.assertTrue(
            hh_aliases.vacancy_title_matches_query(
                {"title": "Оператор производства"}, "manufacturing"
            )
        )
        self.assertTrue(
            hh_aliases.vacancy_title_matches_query(
                {"title": "Teacher"}, "Преподаватель"
            )
        )
        self.assertFalse(
            hh_aliases.vacancy_title_matches_query(
                {"title": "Бухгалтер"}, "Оператор производства"
            )
        )


class SyncHHMarketSkillsTaskTests(APITestCase):
    def setUp(self):
        self.candidate = Candidate.objects.create_user(
            email="candidate@example.com",
            password="testpass123",
        )
        self.domain = Domain.objects.create(name="Digital Marketing")
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Marketing Resume",
            description="I work with analytics and campaigns.",
            position="Digital Marketing Specialist",
            domain=self.domain,
            is_main=True,
        )
        self.google_analytics = Skill.objects.create(name="Google Analytics")
        ResumeSkill.objects.create(
            resume=self.resume,
            skill=self.google_analytics,
            proficiency_level="ADVANCED",
        )

    @patch("apps.general.services.hh_client.collect_hh_api_vacancies")
    def test_sync_creates_market_skills_per_domain(self, mock_collect):
        mock_collect.return_value = [
            {
                "external_id": "123",
                "title": "Digital marketer",
                "company": "HH Company",
                "url": "https://hh.uz/vacancy/123",
                "requirements": ["Google Analytics"],
                "description_requirements": [],
                "key_skills": ["Google Analytics", "SQL"],
            }
        ]

        from apps.general.tasks import sync_hh_market_skills

        result = sync_hh_market_skills(domain_ids=[str(self.domain.id)])

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["market_skills_synced"], 2)
        market_skills = DomainMarketSkill.objects.filter(domain=self.domain)
        self.assertEqual(
            set(market_skills.values_list("skill_name", flat=True)),
            {"Google Analytics", "SQL"},
        )
