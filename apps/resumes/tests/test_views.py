from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.authentication.models import Candidate, Company, Recruiter
from apps.domain.models import Domain
from apps.resumes.models import Resume, ResumeSkill
from apps.skills.models import Skill
from apps.conversations.models import Conversation


class RetrieveResumeViewTests(APITestCase):
    """
    Test suite for the RetrieveResumeView API.

    This endpoint should:
    - Return a single resume by ID with all details and skills
    - Return 404 if resume does not exist
    """

    def setUp(self):
        """
        Prepare initial data:
        - Candidate
        - Two skills
        - One active resume with related skills
        """
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Skills
        self.skill_python = Skill.objects.create(name="Python")
        self.skill_django = Skill.objects.create(name="Django")
        self.domain = Domain.objects.create(name="Software Development")

        # Resume
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Backend Developer Resume",
            description="Experienced in Django and Python",
            is_active=True,
        )

        # Resume skills
        ResumeSkill.objects.create(
            resume=self.resume,
            skill=self.skill_python,
            minimum_years=5,
            proficiency_level="EXPERT",
        )
        ResumeSkill.objects.create(
            resume=self.resume,
            skill=self.skill_django,
            minimum_years=3,
            proficiency_level="ADVANCED",
        )

        self.url = reverse("retrieve-resume", kwargs={"id": str(self.resume.id)})
        self.client.force_authenticate(user=self.candidate)

    def test_retrieve_resume_successfully(self):
        """
        API should return resume with all related fields and skills.
        """
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]

        # Validate resume fields
        assert data["id"] == str(self.resume.id)
        assert data["title"] == "Backend Developer Resume"
        assert data["description"] == "Experienced in Django and Python"

        # Validate skills
        skills = data["resume_skills"]
        skill_names = [s["skill_name"] for s in skills]
        assert "Python" in skill_names
        assert "Django" in skill_names

        # Validate skill details
        python_skill = next(s for s in skills if s["skill_name"] == "Python")
        assert python_skill["proficiency_level"] == "EXPERT"
        assert python_skill["minimum_years"] == 5

    def test_retrieve_resume_ignores_blank_named_skills(self):
        """
        API should not expose invalid resume skills whose skill name is blank.
        """
        self.client.force_authenticate(user=self.candidate)
        blank_skill = Skill.objects.create(name="")
        ResumeSkill.objects.create(resume=self.resume, skill=blank_skill)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        skill_names = [
            s["skill_name"] for s in response.json()["data"]["resume_skills"]
        ]
        assert "" not in skill_names
        assert set(skill_names) == {"Python", "Django"}

    def test_retrieve_non_existent_resume(self):
        """
        API should return 404 if resume does not exist.
        """
        url = reverse(
            "retrieve-resume", kwargs={"id": "11111111-1111-1111-1111-111111111111"}
        )
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_conversation_id_returned_for_recruiter_with_conversation(self):
        """
        When a recruiter with an existing conversation views a resume,
        the conversation_id should be returned.
        """
        # Create a company and recruiter
        company = Company.objects.create(
            name="Test Company",
            tin="123456789",
            is_active=True,
        )
        recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=company,
        )

        # Create a conversation between the recruiter and the candidate
        conversation = Conversation.objects.create(
            candidate=self.candidate,
            recruiter=recruiter,
        )

        # Authenticate as recruiter and fetch the resume
        self.client.force_authenticate(user=recruiter)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        
        # Verify conversation_id is present and matches
        assert "conversation_id" in data
        assert data["conversation_id"] == str(conversation.id)

    def test_conversation_id_none_for_recruiter_without_conversation(self):
        """
        When a recruiter with no existing conversation views a resume,
        the conversation_id should be None.
        """
        # Create a company and recruiter
        company = Company.objects.create(
            name="Test Company",
            tin="123456789",
            is_active=True,
        )
        recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=company,
        )

        # Authenticate as recruiter and fetch the resume (no conversation exists)
        self.client.force_authenticate(user=recruiter)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]

        # Verify conversation_id is None
        assert "conversation_id" in data
        assert data["conversation_id"] is None

    def test_conversation_id_none_for_candidate(self):
        """
        When a candidate views their own resume,
        the conversation_id should be None (only recruiters see this).
        """
        # Authenticate as candidate and fetch the resume
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]

        # Verify conversation_id is None for candidates
        assert "conversation_id" in data
        assert data["conversation_id"] is None

    def test_conversation_id_none_for_unauthenticated_user(self):
        """
        When a candidate views their own resume,
        the conversation_id should be None (only recruiters see this).
        """
        # Authenticated as candidate, no recruiter → no conversation
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]

        # Verify conversation_id is None
        assert "conversation_id" in data
        assert data["conversation_id"] is None


class CreateResumeViewTests(APITestCase):
    """
    Test suite for the CreateResumeView API.

    This endpoint should:
    - Allow only authenticated candidates to create resumes
    - Attach provided skills to the resume
    - Return appropriate errors for invalid cases
    """

    def setUp(self):
        self.client = APIClient()

        # Candidate user
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Recruiter (non-candidate user)
        company = Company.objects.create(
            name="Test Company",
            tin="123456789",
        )
        self.company = Recruiter.objects.create_user(
            email="company@test.com",
            password="testpass123",
            is_recruiter=True,
            company=company,
        )

        # Skills
        self.skill_python = Skill.objects.create(name="Python")
        self.skill_django = Skill.objects.create(name="Django")
        self.domain = Domain.objects.create(name="Software Development")

        self.url = reverse("create-candidate-resume-profile")

        # Valid payload with two skills
        self.valid_payload = {
            "title": "Backend Developer Resume",
            "description": "Experienced backend developer with Python and Django",
            "domain": str(self.domain.id),
            "skills_data": [
                {
                    "skill_id": self.skill_python.id,
                    "minimum_years": 5,
                    "proficiency_level": "ADVANCED",
                },
                {
                    "skill_id": self.skill_django.id,
                    "minimum_years": 3,
                    "proficiency_level": "INTERMEDIATE",
                },
            ],
        }

    def test_create_resume_successfully(self):
        """
        Candidate should be able to create resume successfully
        """
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(self.url, self.valid_payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]

        # Core fields
        assert data["title"] == "Backend Developer Resume"
        assert (
                data["description"]
                == "Experienced backend developer with Python and Django"
        )

        # Skills must be created
        skills = data["resume_skills"]
        skill_names = [s["skill_name"] for s in skills]
        assert "Python" in skill_names
        assert "Django" in skill_names

    def test_create_resume_as_non_candidate(self):
        """
        Non-candidate user should not be able to create a resume
        """
        self.client.force_authenticate(user=self.company)
        response = self.client.post(self.url, self.valid_payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Candidate profile not found" in str(response.data)

    def test_unauthenticated_user_cannot_create(self):
        """
        Unauthenticated users should not be able to create resumes
        """
        response = self.client.post(self.url, self.valid_payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_resume_without_skills(self):
        """
        Candidate should be able to create resume without skills
        """
        self.client.force_authenticate(user=self.candidate)
        payload = {
            "title": "Junior Developer Resume",
            "description": "Entry-level developer",
            "domain": str(self.domain.id),
        }
        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]
        assert data["resume_skills"] == []

    def test_create_resume_requires_domain(self):
        """
        Candidate must select a domain when creating a resume.
        """
        self.client.force_authenticate(user=self.candidate)
        payload = {
            "title": "Junior Developer Resume",
            "description": "Entry-level developer",
        }
        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "domain" in str(response.data)


class CandidateResumeListViewTests(APITestCase):
    """
    Test suite for the CandidateResumeListView API.

    This endpoint should:
    - Allow candidates to see only their own resumes
    - Return empty list if candidate has no resumes
    - Prevent companies and unauthenticated users from accessing candidate resumes
    """

    def setUp(self):
        self.client = APIClient()

        # Candidate user
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Another candidate
        self.other_candidate = Candidate.objects.create_user(
            email="other@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Non-candidate user (recruiter with is_candidate=False)
        self.company = Recruiter.objects.create_user(
            email="company@test.com",
            password="testpass123",
        )

        self.url = reverse("candidate-resume-list")

    def test_list_candidate_resumes_successfully(self):
        """
        Candidate should see only their own resumes
        """
        # Create resumes for this candidate
        Resume.objects.create(
            title="Backend Developer",
            description="Python expert",
            candidate=self.candidate,
        )
        Resume.objects.create(
            title="Frontend Developer",
            description="React expert",
            candidate=self.candidate,
        )

        # Create resume for other candidate (should not appear)
        Resume.objects.create(
            title="Other Resume",
            description="Not mine",
            candidate=self.other_candidate,
        )

        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        results = data["data"]
        assert len(results) == 2

        titles = [v["title"] for v in results]
        assert "Backend Developer" in titles
        assert "Frontend Developer" in titles
        assert "Other Resume" not in titles

    def test_candidate_with_no_resumes(self):
        """
        Candidate should get an empty list if they have no resumes
        """
        self.client.force_authenticate(user=self.candidate)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["data"]
        assert results == []

    def test_company_cannot_see_resumes(self):
        """
        Company should not see candidate resumes
        """
        self.client.force_authenticate(user=self.company)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        results = data["data"]
        assert results == []

    def test_unauthenticated_user_cannot_access(self):
        """
        Unauthenticated users should not have access
        """
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class ResumeSkillIntegrationTests(APITestCase):
    """
    Integration tests for resume skills functionality.
    """

    def setUp(self):
        self.client = APIClient()

        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        self.skill1 = Skill.objects.create(name="React")
        self.skill2 = Skill.objects.create(name="Node.js")
        self.skill3 = Skill.objects.create(name="TypeScript")
        self.domain = Domain.objects.create(name="Software Development")

        self.url = reverse("create-candidate-resume-profile")

    def test_create_resume_with_multiple_skills(self):
        """
        Test creating resume with multiple skills and proficiency levels
        """
        self.client.force_authenticate(user=self.candidate)

        payload = {
            "title": "Full-Stack Developer",
            "description": "Expert in modern web technologies",
            "domain": str(self.domain.id),
            "skills_data": [
                {
                    "skill_id": self.skill1.id,
                    "proficiency_level": "EXPERT",
                    "minimum_years": 6,
                },
                {
                    "skill_id": self.skill2.id,
                    "proficiency_level": "ADVANCED",
                    "minimum_years": 5,
                },
                {
                    "skill_id": self.skill3.id,
                    "proficiency_level": "INTERMEDIATE",
                    "minimum_years": 2,
                },
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()["data"]

        # Verify all skills are present
        skills = data["resume_skills"]
        assert len(skills) == 3

        # Verify skill details
        react_skill = next(s for s in skills if s["skill_name"] == "React")
        assert react_skill["proficiency_level"] == "EXPERT"
        assert react_skill["minimum_years"] == 6

    def test_invalid_skill_id(self):
        """
        Test that invalid skill ID returns proper error
        """
        self.client.force_authenticate(user=self.candidate)

        payload = {
            "title": "Developer",
            "description": "Test",
            "domain": str(self.domain.id),
            "skills_data": [
                {
                    "skill_id": 99999,  # Invalid
                    "proficiency_level": "INTERMEDIATE",
                }
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "skills_data" in str(response.data)

    def test_invalid_proficiency_level(self):
        """
        Test that invalid proficiency level returns proper error
        """
        self.client.force_authenticate(user=self.candidate)

        payload = {
            "title": "Developer",
            "description": "Test",
            "domain": str(self.domain.id),
            "skills_data": [
                {
                    "skill_id": self.skill1.id,
                    "proficiency_level": "INVALID",  # Invalid
                }
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
