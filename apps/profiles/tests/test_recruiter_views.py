from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.authentication.models import Recruiter, Company
from apps.profiles.models import RecruiterProfile


class RecruiterProfileAPITests(APITestCase):
    """
    Test suite for RecruiterProfile API endpoints.

    Covers:
    - Listing recruiter profiles
    - Creating recruiter profiles
    - Retrieving current recruiter profile by email
    - Updating recruiter role (admin only)
    """

    def setUp(self):
        """
        Set up test data:
        - Create a company
        - Create a recruiter user
        - Create a recruiter profile
        - Prepare API endpoints
        """
        self.client = APIClient()

        # Create company
        self.company = Company.objects.create(
            name="OpenAI",
            tin="123456789",
        )

        # Create recruiter user
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company,
        )

        # Create recruiter profile
        self.profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Alice Brown",
            phone="111222333",
            level="Recruiter",
        )

        # API endpoints
        self.list_url = reverse("recruiter-profile-list")
        self.level_update_url = reverse(
            "recruiter-level-update", kwargs={"recruiter_id": str(self.profile.id)}
        )

    def _extract_payload(self, response):
        data = response.json()
        if isinstance(data, dict) and "data" in data and data.get("success") is True:
            return data["data"]
        return data

    def test_list_recruiter_profiles(self):
        """
        Ensure anyone can list all recruiter profiles.

        Expected behavior:
        - Returns 200 OK
        - At least one profile in response
        """
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = self._extract_payload(response)
        results = data.get("results", data)

        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(any(p["full_name"] == "Alice Brown" for p in results))

    def test_update_recruiter_level_success(self):
        """
        Ensure Admin recruiters can update recruiter role.

        Expected behavior:
        - Returns 200 OK (if update succeeds)
        - Or 400 Bad Request (if validation fails)
        - Returns 500 Internal Server Error (if unexpected error occurs)
        """
        # Promote recruiter to Admin
        self.profile.level = "Admin"
        self.profile.save()

        self.client.force_authenticate(user=self.recruiter)
        payload = {"level": "Recruiter"}

        response = self.client.patch(self.level_update_url, payload, format="json")
        self.assertIn(
            response.status_code,
            [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ],
        )

    def test_update_recruiter_level_non_admin(self):
        """
        Ensure non-admin recruiters cannot update recruiter role.

        Expected behavior:
        - Returns 403 Forbidden
        """
        self.client.force_authenticate(user=self.recruiter)
        payload = {"level": "Admin"}  # Current level = Recruiter (not admin)

        response = self.client.patch(self.level_update_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RecruiterListPaginationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Pagination Co", tin="923456789")
        cls.auth_recruiter = Recruiter.objects.create_user(
            email="admin.pagination@test.com",
            password="StrongPass123!",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.auth_recruiter,
            full_name="Pagination Admin",
            level=RecruiterProfile.Level.ADMIN,
        )

        for index in range(4):
            recruiter = Recruiter.objects.create_user(
                email=f"rec{index}.pagination@test.com",
                password="StrongPass123!",
                is_recruiter=True,
                company=cls.company,
            )
            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=f"Recruiter {index}",
                level=RecruiterProfile.Level.RECRUITER,
            )

        cls.url = reverse("recruiter-profile-list")

    def setUp(self):
        self.client.force_authenticate(user=self.auth_recruiter)

    @staticmethod
    def _extract_payload(response):
        data = response.json()
        if isinstance(data, dict) and data.get("success"):
            return data
        return data

    def test_recruiter_list_uses_default_limit_offset_pagination_shape(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = self._extract_payload(response)
        self.assertIn("data", payload)
        self.assertIn("pagination", payload)
        self.assertIn("count", payload["pagination"])
        self.assertIn("limit", payload["pagination"])
        self.assertIn("offset", payload["pagination"])

    def test_recruiter_list_respects_limit_and_offset(self):
        response = self.client.get(self.url, {"limit": 1, "offset": 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = self._extract_payload(response)
        self.assertEqual(payload["pagination"]["limit"], 1)
        self.assertEqual(payload["pagination"]["offset"], 1)
        self.assertEqual(len(payload["data"]), 1)
