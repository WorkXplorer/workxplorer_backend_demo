from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from apps.applications.models import JobApplication, ApplicationStatus
from apps.profiles.models import RecruiterProfile
from apps.authentication.models import Recruiter, Candidate, Company
from apps.vacancies.models import Vacancy


class HiredCandidatesListViewTests(APITestCase):
    """
    Test suite for the HiredCandidatesListView API endpoint.
    This endpoint returns the list of candidates hired by the company.
    Only accessible by admin recruiters.
    """

    @classmethod
    def setUpTestData(cls):
        """
        Set up test data:
        - Company with admin and regular recruiters
        - Candidates with profiles
        - Vacancies and applications with OFFER_ACCEPTED status
        """
        from apps.profiles.models import CandidateProfile

        cls.company = Company.objects.create(
            name="Hired Candidates Test Company",
            tin="111222333",
        )

        # Create admin recruiter
        cls.admin_recruiter = Recruiter.objects.create_user(
            email="hired_admin@example.com",
            password="adminpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.admin_recruiter,
            full_name="Admin for Hired Candidates",
            level=RecruiterProfile.Level.ADMIN,
        )

        # Create regular recruiter for permission testing
        cls.regular_recruiter = Recruiter.objects.create_user(
            email="hired_regular@example.com",
            password="regularpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.regular_recruiter,
            full_name="Regular Recruiter",
            level=RecruiterProfile.Level.RECRUITER,
        )

        # Create candidates with profiles
        cls.hired_candidate1 = Candidate.objects.create_user(
            email="hired_candidate1@example.com",
            password="candidatepass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=cls.hired_candidate1,
            full_name="Hired Candidate One",
            phone="+998901111111",
        )

        cls.hired_candidate2 = Candidate.objects.create_user(
            email="hired_candidate2@example.com",
            password="candidatepass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=cls.hired_candidate2,
            full_name="Hired Candidate Two",
            phone="+998902222222",
        )

        cls.not_hired_candidate = Candidate.objects.create_user(
            email="not_hired@example.com",
            password="candidatepass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=cls.not_hired_candidate,
            full_name="Not Hired Candidate",
            phone="+998903333333",
        )

        # Create vacancies
        cls.vacancy1 = Vacancy.objects.create(
            title="Senior Python Developer",
            company=cls.company,
            created_by=cls.admin_recruiter,
        )

        cls.vacancy2 = Vacancy.objects.create(
            title="Data Analyst",
            company=cls.company,
            created_by=cls.admin_recruiter,
        )

        # Create hired applications (OFFER_ACCEPTED status)
        cls.hired_app1 = JobApplication.objects.create(
            candidate=cls.hired_candidate1,
            vacancy=cls.vacancy1,
            status=ApplicationStatus.OFFER_ACCEPTED,
            hired_at=timezone.now(),
        )

        cls.hired_app2 = JobApplication.objects.create(
            candidate=cls.hired_candidate2,
            vacancy=cls.vacancy2,
            status=ApplicationStatus.OFFER_ACCEPTED,
            hired_at=timezone.now(),
        )

        # Create non-hired application
        cls.not_hired_app = JobApplication.objects.create(
            candidate=cls.not_hired_candidate,
            vacancy=cls.vacancy1,
            status=ApplicationStatus.APPLIED,
        )

        cls.url = reverse("hired-candidates")

    def test_admin_can_access_hired_candidates(self):
        """
        Ensure admin recruiters can access the hired candidates list.
        """
        self.client.force_authenticate(user=self.admin_recruiter)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_regular_recruiter_cannot_access(self):
        """
        Ensure regular recruiters cannot access this endpoint.
        """
        self.client.force_authenticate(user=self.regular_recruiter)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access(self):
        """
        Ensure unauthenticated users cannot access this endpoint.
        """
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_response_contains_required_fields(self):
        """
        Ensure response contains all required fields.
        """
        self.client.force_authenticate(user=self.admin_recruiter)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]
        self.assertGreater(len(results), 0)

        # Check first result has all required fields
        first_result = results[0]
        self.assertIn("full_name", first_result)
        self.assertIn("title", first_result)
        self.assertIn("hired_at", first_result)
        self.assertIn("phone_number", first_result)

    def test_filter_by_full_name(self):
        """
        Ensure filtering by candidate full_name works.
        """
        self.client.force_authenticate(user=self.admin_recruiter)
        response = self.client.get(self.url, {"search": "One"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["full_name"], "Hired Candidate One")

    def test_filter_by_title(self):
        """
        Ensure filtering by vacancy title works.
        """
        self.client.force_authenticate(user=self.admin_recruiter)
        response = self.client.get(self.url, {"search": "Python"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["title"], "Senior Python Developer")

    def test_only_offer_accepted_returned(self):
        """
        Ensure only candidates with OFFER_ACCEPTED status are returned.
        """
        self.client.force_authenticate(user=self.admin_recruiter)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should only return 2 hired candidates, not the APPLIED one
        self.assertEqual(response.data["count"], 2)

        # Verify the not_hired_candidate is not in the results
        full_names = [r["full_name"] for r in response.data["results"]]
        self.assertNotIn("Not Hired Candidate", full_names)
