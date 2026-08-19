from django.test import TestCase
from django.db.utils import IntegrityError
from datetime import date

from apps.resumes.models import Resume, ResumeSkill, ResumeExperience, ResumeContact
from apps.resumes.models.choices import ProficiencyLevel
from apps.authentication.models import Candidate
from apps.skills.models import Skill


class ResumeSkillModelTests(TestCase):
    """Test suite for ResumeSkill model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )
        cls.resume = Resume.objects.create(
            candidate=cls.candidate, title="My Resume", description="Software Developer"
        )
        cls.skill = Skill.objects.create(name="Python")

    def test_create_resume_skill_successfully(self):
        """Test creating a resume skill with valid data."""
        resume_skill = ResumeSkill.objects.create(
            resume=self.resume,
            skill=self.skill,
            minimum_years=3,
            proficiency_level=ProficiencyLevel.ADVANCED,
        )

        self.assertEqual(resume_skill.resume, self.resume)
        self.assertEqual(resume_skill.skill, self.skill)
        self.assertEqual(resume_skill.minimum_years, 3)
        self.assertEqual(resume_skill.proficiency_level, ProficiencyLevel.ADVANCED)

    def test_resume_skill_string_representation(self):
        """Test the string representation of ResumeSkill."""
        resume_skill = ResumeSkill.objects.create(
            resume=self.resume,
            skill=self.skill,
            proficiency_level=ProficiencyLevel.EXPERT,
        )

        expected_str = (
            f"{self.resume.title} — {self.skill.name} ({ProficiencyLevel.EXPERT})"
        )
        self.assertEqual(str(resume_skill), expected_str)

    def test_resume_skill_unique_constraint(self):
        """Test that resume-skill combination must be unique."""
        ResumeSkill.objects.create(resume=self.resume, skill=self.skill)

        with self.assertRaises(IntegrityError):
            ResumeSkill.objects.create(resume=self.resume, skill=self.skill)

    def test_resume_skill_default_values(self):
        """Test default values for ResumeSkill."""
        resume_skill = ResumeSkill.objects.create(resume=self.resume, skill=self.skill)

        self.assertEqual(resume_skill.minimum_years, 0)
        self.assertEqual(resume_skill.proficiency_level, ProficiencyLevel.INTERMEDIATE)


class ResumeExperienceModelTests(TestCase):
    """Test suite for ResumeExperience model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )
        cls.resume = Resume.objects.create(
            candidate=cls.candidate,
            title="My Resume",
            description="Experienced Developer",
        )

    def test_create_resume_experience_successfully(self):
        """Test creating a resume experience with valid data."""
        experience = ResumeExperience.objects.create(
            resume=self.resume,
            company="Tech Corp",
            role="Software Engineer",
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
            description="Developed web applications",
        )

        self.assertEqual(experience.resume, self.resume)
        self.assertEqual(experience.company, "Tech Corp")
        self.assertEqual(experience.role, "Software Engineer")
        self.assertEqual(experience.start_date, date(2020, 1, 1))
        self.assertEqual(experience.end_date, date(2023, 12, 31))

    def test_resume_experience_string_representation(self):
        """Test the string representation of ResumeExperience."""
        experience = ResumeExperience.objects.create(
            resume=self.resume, company="Startup Inc", role="Lead Developer"
        )

        self.assertEqual(str(experience), "Lead Developer at Startup Inc")

    def test_resume_experience_ordering(self):
        """Test that experiences are ordered by start_date descending."""
        exp1 = ResumeExperience.objects.create(
            resume=self.resume,
            company="Company A",
            role="Junior Dev",
            start_date=date(2018, 1, 1),
        )
        exp2 = ResumeExperience.objects.create(
            resume=self.resume,
            company="Company B",
            role="Senior Dev",
            start_date=date(2022, 1, 1),
        )

        experiences = ResumeExperience.objects.all()

        # Most recent first
        self.assertEqual(experiences[0].id, exp2.id)
        self.assertEqual(experiences[1].id, exp1.id)


class ResumeContactModelTests(TestCase):
    """Test suite for ResumeContact model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )
        cls.resume = Resume.objects.create(
            candidate=cls.candidate, title="My Resume", description="Developer Resume"
        )

    def test_create_resume_contact_successfully(self):
        """Test creating a resume contact with valid data."""
        contact = ResumeContact.objects.create(
            resume=self.resume, type="EMAIL", value="john@example.com"
        )

        self.assertEqual(contact.resume, self.resume)
        self.assertEqual(contact.type, "EMAIL")
        self.assertEqual(contact.value, "john@example.com")

    def test_resume_contact_string_representation(self):
        """Test the string representation of ResumeContact."""
        contact = ResumeContact.objects.create(
            resume=self.resume, type="PHONE", value="+998901234567"
        )

        expected_str = "Phone: +998901234567"
        self.assertEqual(str(contact), expected_str)

    def test_resume_contact_types(self):
        """Test different contact types."""
        contact_types = ["EMAIL", "PHONE", "LINKEDIN", "GITHUB", "PORTFOLIO"]

        for i, contact_type in enumerate(contact_types):
            contact = ResumeContact.objects.create(
                resume=self.resume, type=contact_type, value=f"value_{i}"
            )
            self.assertEqual(contact.type, contact_type)

    def test_resume_contact_unique_together(self):
        """Test that resume-type-value combination must be unique."""
        ResumeContact.objects.create(
            resume=self.resume, type="EMAIL", value="test@example.com"
        )

        with self.assertRaises(IntegrityError):
            ResumeContact.objects.create(
                resume=self.resume, type="EMAIL", value="test@example.com"
            )


class ResumeModelTests(TestCase):
    """Test suite for Resume model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )

    def test_create_resume_successfully(self):
        """Test creating a resume with valid data."""
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="Software Developer Resume",
            description="Experienced full-stack developer",
        )

        self.assertEqual(resume.candidate, self.candidate)
        self.assertEqual(resume.title, "Software Developer Resume")
        self.assertEqual(resume.description, "Experienced full-stack developer")
        self.assertTrue(resume.is_active)
        self.assertIsNotNone(resume.created_at)

    def test_resume_default_is_active(self):
        """Test that resume is active by default."""
        resume = Resume.objects.create(
            candidate=self.candidate, title="Active Resume", description="Description"
        )

        self.assertTrue(resume.is_active)

    def test_resume_inactive_status(self):
        """Test creating an inactive resume."""
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="Inactive Resume",
            description="Description",
            is_active=False,
        )

        self.assertFalse(resume.is_active)

    def test_resume_with_skills(self):
        """Test adding skills to resume through ResumeSkill."""
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="Developer Resume",
            description="Skills-based resume",
        )

        skill1 = Skill.objects.create(name="JavaScript")
        skill2 = Skill.objects.create(name="React")

        ResumeSkill.objects.create(
            resume=resume, skill=skill1, proficiency_level=ProficiencyLevel.ADVANCED
        )
        ResumeSkill.objects.create(
            resume=resume, skill=skill2, proficiency_level=ProficiencyLevel.INTERMEDIATE
        )

        self.assertEqual(resume.skills.count(), 2)
        self.assertIn(skill1, resume.skills.all())
        self.assertIn(skill2, resume.skills.all())

    def test_resume_with_experiences(self):
        """Test adding experiences to resume."""
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="Experienced Developer",
            description="Multiple positions",
        )

        ResumeExperience.objects.create(
            resume=resume, company="Company A", role="Developer"
        )
        ResumeExperience.objects.create(
            resume=resume, company="Company B", role="Senior Developer"
        )

        self.assertEqual(resume.experiences.count(), 2)

    def test_resume_with_contacts(self):
        """Test adding contacts to resume."""
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="Contact Resume",
            description="With contact info",
        )

        ResumeContact.objects.create(
            resume=resume, type="EMAIL", value="test@example.com"
        )
        ResumeContact.objects.create(resume=resume, type="PHONE", value="+998901234567")

        self.assertEqual(resume.contacts.count(), 2)

    def test_resume_embedding_fields(self):
        """Test resume embedding-related fields."""
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="ML Resume",
            description="Machine Learning Engineer",
        )

        self.assertIsNone(resume.embedding)
        self.assertIsNone(resume.combined_text_en)
