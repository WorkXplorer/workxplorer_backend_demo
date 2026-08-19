from django.test import TestCase
from django.db.utils import IntegrityError
from decimal import Decimal

from apps.vacancies.models import FavouriteVacancy, Vacancy, VacancySkill
from apps.authentication.models import Candidate, Company, Recruiter
from apps.skills.models import Skill
from apps.domain.models import Domain


class VacancySkillModelTests(TestCase):
    """Test suite for VacancySkill model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123", company=cls.company
        )
        cls.vacancy = Vacancy.objects.create(
            title="Software Engineer", company=cls.company, created_by=cls.recruiter
        )
        cls.skill = Skill.objects.create(name="Python")

    def test_create_vacancy_skill_successfully(self):
        """Test creating a vacancy skill with valid data."""
        vacancy_skill = VacancySkill.objects.create(
            vacancy=self.vacancy,
            skill=self.skill,
            is_required=True,
            minimum_years=2,
            proficiency_level="INTERMEDIATE",
        )

        self.assertEqual(vacancy_skill.vacancy, self.vacancy)
        self.assertEqual(vacancy_skill.skill, self.skill)
        self.assertTrue(vacancy_skill.is_required)
        self.assertEqual(vacancy_skill.minimum_years, 2)
        self.assertEqual(vacancy_skill.proficiency_level, "INTERMEDIATE")

    def test_vacancy_skill_default_values(self):
        """Test default values for VacancySkill."""
        vacancy_skill = VacancySkill.objects.create(
            vacancy=self.vacancy, skill=self.skill
        )

        self.assertTrue(vacancy_skill.is_required)
        self.assertEqual(vacancy_skill.minimum_years, 0)
        self.assertEqual(vacancy_skill.proficiency_level, "UNDEFINED")

    def test_vacancy_skill_unique_together(self):
        """Test that vacancy-skill combination must be unique."""
        VacancySkill.objects.create(vacancy=self.vacancy, skill=self.skill)

        with self.assertRaises(IntegrityError):
            VacancySkill.objects.create(vacancy=self.vacancy, skill=self.skill)

    def test_vacancy_skill_proficiency_levels(self):
        """Test different proficiency levels."""
        levels = ["BEGINNER", "INTERMEDIATE", "ADVANCED", "EXPERT"]

        for level in levels:
            skill = Skill.objects.create(name=f"Skill-{level}")
            vacancy_skill = VacancySkill.objects.create(
                vacancy=self.vacancy, skill=skill, proficiency_level=level
            )
            self.assertEqual(vacancy_skill.proficiency_level, level)


class VacancyModelTests(TestCase):
    """Test suite for Vacancy model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123", company=cls.company
        )

    def test_create_vacancy_successfully(self):
        """Test creating a vacancy with valid data."""
        vacancy = Vacancy.objects.create(
            title="Backend Developer",
            company=self.company,
            created_by=self.recruiter,
            requirements="Python, Django, PostgreSQL",
            responsibilities="Build APIs",
            about_us="We are a tech company",
            additional_info="Great benefits",
        )

        self.assertEqual(vacancy.title, "Backend Developer")
        self.assertEqual(vacancy.company, self.company)
        self.assertEqual(vacancy.created_by, self.recruiter)
        self.assertTrue(vacancy.is_active)
        self.assertIsNotNone(vacancy.created_at)
        self.assertIsNotNone(vacancy.updated_at)

    def test_vacancy_string_representation(self):
        """Test the string representation of Vacancy."""
        vacancy = Vacancy.objects.create(
            title="Data Scientist", company=self.company, created_by=self.recruiter
        )

        expected_str = (
            f"Data Scientist from {self.company}, created at {vacancy.created_at}"
        )
        self.assertEqual(str(vacancy), expected_str)

    def test_vacancy_with_salary_range(self):
        """Test creating a vacancy with salary range."""
        vacancy = Vacancy.objects.create(
            title="Frontend Developer",
            company=self.company,
            created_by=self.recruiter,
            salary_min=Decimal("50000.00"),
            salary_max=Decimal("80000.00"),
            salary_currency="USD",
        )

        self.assertEqual(vacancy.salary_min, Decimal("50000.00"))
        self.assertEqual(vacancy.salary_max, Decimal("80000.00"))
        self.assertEqual(vacancy.salary_currency, "USD")

    def test_vacancy_employment_type(self):
        """Test different employment types."""
        employment_types = ["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP"]

        for emp_type in employment_types:
            vacancy = Vacancy.objects.create(
                title=f"{emp_type} Position",
                company=self.company,
                created_by=self.recruiter,
                employment_type=emp_type,
            )
            self.assertEqual(vacancy.employment_type, emp_type)

    def test_vacancy_employment_format(self):
        """Test different employment formats."""
        formats = ["ON_SITE", "REMOTE", "HYBRID"]

        for format_type in formats:
            vacancy = Vacancy.objects.create(
                title=f"{format_type} Job",
                company=self.company,
                created_by=self.recruiter,
                employment_format=format_type,
            )
            self.assertEqual(vacancy.employment_format, format_type)

    def test_vacancy_with_domain(self):
        """Test creating a vacancy with a domain."""
        domain = Domain.objects.create(name="Information Technology")

        vacancy = Vacancy.objects.create(
            title="Software Engineer",
            company=self.company,
            created_by=self.recruiter,
            domain=domain,
        )

        self.assertEqual(vacancy.domain, domain)

    def test_vacancy_with_contact_info(self):
        """Test creating a vacancy with contact information."""
        vacancy = Vacancy.objects.create(
            title="HR Manager",
            company=self.company,
            created_by=self.recruiter,
            contact_email="hr@company.com",
            contact_phone="+998901234567",
        )

        self.assertEqual(vacancy.contact_email, "hr@company.com")
        self.assertEqual(vacancy.contact_phone, "+998901234567")

    def test_vacancy_with_experience_requirement(self):
        """Test creating a vacancy with experience requirement."""
        vacancy = Vacancy.objects.create(
            title="Senior Developer",
            company=self.company,
            created_by=self.recruiter,
            experience=5,
        )

        self.assertEqual(vacancy.experience, 5)

    def test_vacancy_with_skills(self):
        """Test adding skills to vacancy through VacancySkill."""
        vacancy = Vacancy.objects.create(
            title="Full Stack Developer",
            company=self.company,
            created_by=self.recruiter,
        )

        skill1 = Skill.objects.create(name="JavaScript")
        skill2 = Skill.objects.create(name="React")

        VacancySkill.objects.create(vacancy=vacancy, skill=skill1, is_required=True)
        VacancySkill.objects.create(vacancy=vacancy, skill=skill2, is_required=False)

        self.assertEqual(vacancy.required_skills.count(), 2)
        self.assertIn(skill1, vacancy.required_skills.all())
        self.assertIn(skill2, vacancy.required_skills.all())

    def test_vacancy_default_is_active(self):
        """Test that vacancy is active by default."""
        vacancy = Vacancy.objects.create(
            title="QA Engineer", company=self.company, created_by=self.recruiter
        )

        self.assertTrue(vacancy.is_active)

    def test_vacancy_inactive_status(self):
        """Test creating an inactive vacancy."""
        vacancy = Vacancy.objects.create(
            title="Closed Position",
            company=self.company,
            created_by=self.recruiter,
            is_active=False,
        )

        self.assertFalse(vacancy.is_active)

    def test_vacancy_ordering(self):
        """Test that vacancies are ordered by created_at descending."""
        vacancy1 = Vacancy.objects.create(
            title="First Job", company=self.company, created_by=self.recruiter
        )
        vacancy2 = Vacancy.objects.create(
            title="Second Job", company=self.company, created_by=self.recruiter
        )

        vacancies = Vacancy.objects.all()

        # Most recent first
        self.assertEqual(vacancies[0].id, vacancy2.id)
        self.assertEqual(vacancies[1].id, vacancy1.id)

    def test_get_text_for_embedding_method(self):
        """Test the get_text_for_embedding method."""
        vacancy = Vacancy.objects.create(
            title="ML Engineer",
            company=self.company,
            created_by=self.recruiter,
            requirements="Python, TensorFlow, PyTorch",
        )

        text = vacancy.get_text_for_embedding()

        self.assertIn("ML Engineer", text)
        self.assertIn("Python, TensorFlow, PyTorch", text)

    def test_vacancy_embedding_fields(self):
        """Test vacancy embedding-related fields."""
        vacancy = Vacancy.objects.create(
            title="AI Researcher",
            company=self.company,
            created_by=self.recruiter,
            is_embedded=False,
        )

        self.assertFalse(vacancy.is_embedded)
        self.assertIsNone(vacancy.embedding)
        self.assertIsNone(vacancy.combined_text_en)


class FavouriteVacancyModelTests(TestCase):
    """Test suite for FavouriteVacancy through model."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Favourite Co", tin="555444333")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter-favourite@test.com",
            password="testpass123",
            company=cls.company,
        )
        cls.candidate = Candidate.objects.create_user(
            email="candidate-favourite@test.com",
            password="testpass123",
            is_candidate=True,
        )
        cls.vacancy = Vacancy.objects.create(
            title="Data Analyst",
            company=cls.company,
            created_by=cls.recruiter,
        )

    def test_create_favourite_vacancy_successfully(self):
        favourite = FavouriteVacancy.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
        )

        self.assertEqual(favourite.candidate, self.candidate)
        self.assertEqual(favourite.vacancy, self.vacancy)
        self.assertIsNotNone(favourite.created_at)

    def test_unique_candidate_vacancy_constraint(self):
        FavouriteVacancy.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
        )

        with self.assertRaises(IntegrityError):
            FavouriteVacancy.objects.create(
                candidate=self.candidate,
                vacancy=self.vacancy,
            )
