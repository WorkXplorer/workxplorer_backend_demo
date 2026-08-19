from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
import numpy as np

from apps.authentication.models import Candidate, Recruiter, Company
from apps.resumes.models import Resume
from apps.vacancies.models import Vacancy


class MatchResumeToVacanciesViewTests(APITestCase):
    """
    Test matching resumes to vacancies.
    """

    def setUp(self):
        self.client = APIClient()

        # Create candidate
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Create resume with embedding
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Python Developer Resume",
            description="Experienced Python developer",
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),  # Random embedding for testing
        )

        # Create company and recruiter
        self.company = Company.objects.create(name="TechCorp", tin="123456789")
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company,
        )

        # Create vacancies with embeddings
        self.vacancy1 = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Senior Python Developer",
            is_active=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

        self.vacancy2 = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Frontend Developer",
            is_active=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

    def test_match_resume_to_vacancies_success(self):
        """Test successful matching of resume to vacancies."""
        self.client.force_authenticate(user=self.candidate)

        url = reverse("match-resume-to-vacancies", kwargs={"resume_id": self.resume.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]

        # Verify response structure
        self.assertIn("resume_id", data)
        self.assertIn("resume_title", data)
        self.assertIn("matches_found", data)
        self.assertIn("matches", data)

        # Verify matches have required fields
        if data["matches_found"] > 0:
            match = data["matches"][0]
            self.assertIn("vacancy", match)
            self.assertIn("similarity_score", match)
            self.assertIn("match_percentage", match)
            self.assertIn("match_quality", match)

    def test_match_resume_without_embedding(self):
        """Test matching resume without embedding returns error."""
        # Create resume without embedding
        resume_no_embedding = Resume.objects.create(
            candidate=self.candidate,
            title="Incomplete Resume",
            description="No embedding yet",
            is_embedded=False,
        )

        self.client.force_authenticate(user=self.candidate)

        url = reverse(
            "match-resume-to-vacancies", kwargs={"resume_id": resume_no_embedding.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()["success"])

    def test_match_requires_authentication(self):
        """Test that matching requires authentication."""
        url = reverse("match-resume-to-vacancies", kwargs={"resume_id": self.resume.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_match_with_custom_parameters(self):
        """Test matching with custom top_k and min_similarity."""
        self.client.force_authenticate(user=self.candidate)

        url = reverse("match-resume-to-vacancies", kwargs={"resume_id": self.resume.id})
        response = self.client.get(url, {"top_k": 5, "min_similarity": 0.6})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]

        # Should respect top_k limit
        self.assertLessEqual(data["matches_found"], 5)


class MatchVacancyToResumesViewTests(APITestCase):
    """
    Test matching vacancies to resumes.
    """

    def setUp(self):
        self.client = APIClient()

        # Create company and recruiter
        self.company = Company.objects.create(name="TechCorp", tin="123456789")
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company,
        )

        # Create vacancy with embedding
        self.vacancy = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Senior Developer",
            is_active=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

        # Create candidates with resumes
        self.candidate1 = Candidate.objects.create_user(
            email="candidate1@test.com",
            password="testpass123",
            is_candidate=True,
        )

        self.resume1 = Resume.objects.create(
            candidate=self.candidate1,
            title="Python Expert",
            description="10 years Python experience",
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

    def test_match_vacancy_to_resumes_success(self):
        """Test successful matching of vacancy to resumes."""
        self.client.force_authenticate(user=self.recruiter)

        url = reverse(
            "match-vacancy-to-resumes", kwargs={"vacancy_id": self.vacancy.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]

        # Verify response structure
        self.assertIn("vacancy_id", data)
        self.assertIn("vacancy_title", data)
        self.assertIn("company_name", data)
        self.assertIn("matches_found", data)
        self.assertIn("matches", data)

    def test_match_vacancy_without_embedding(self):
        """Test matching vacancy without embedding returns error."""
        vacancy_no_embedding = Vacancy.objects.create(
            created_by=self.recruiter,
            company=self.company,
            title="Incomplete Vacancy",
            is_embedded=False,
        )

        self.client.force_authenticate(user=self.recruiter)

        url = reverse(
            "match-vacancy-to-resumes", kwargs={"vacancy_id": vacancy_no_embedding.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
