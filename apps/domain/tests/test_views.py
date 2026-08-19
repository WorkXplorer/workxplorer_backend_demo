from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from apps.domain.models import Domain, HrCreatedProfession
from apps.authentication.models import CustomUser, Company


class DomainDetailAPIViewTests(APITestCase):
    """Test suite for DomainDetailAPIView."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.user = CustomUser.objects.create_superuser(  # Create a superuser
            email="testadmin@example.com",
            password="testpassword",
            is_active=True,
        )
        cls.domain = Domain.objects.create(name="Technology", description="Tech domain")

    def setUp(self):
        """Authenticate the test client."""
        self.client.force_authenticate(user=self.user)

    def test_retrieve_domain_successfully(self):
        """Test retrieving a specific domain."""
        url = reverse("domain-detail", kwargs={"pk": self.domain.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["name"], "Technology")
        self.assertEqual(data["description"], "Tech domain")

    def test_retrieve_nonexistent_domain(self):
        """Test retrieving a domain that doesn't exist."""
        url = reverse(
            "domain-detail", kwargs={"pk": 9999}
        )  # Use a non-existent numeric ID
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ponytail: DomainDetailAPIView is read-only (RetrieveAPIView).
    # PUT, PATCH, and DELETE are intentionally not supported.


class DomainListNamesAPIViewTests(APITestCase):
    """Test suite for DomainListNamesAPIView."""

    def setUp(self):
        """Authenticate the test client."""
        self.user = CustomUser.objects.create_user(
            email="testuser@example.com",
            password="testpassword",
            is_active=True,
        )
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")


class HrCreatedProfessionListCreateAPIViewTests(APITestCase):
    """
    Test suite for HrCreatedProfessionListCreateAPIView.
    This includes tests for listing and creating HR created professions.
    """

    def setUp(self):
        from apps.authentication.models import Recruiter
        self.company = Company.objects.create(name="Test Company", is_active=True)
        self.user = Recruiter.objects.create_user(
            email="testuser@example.com",
            password="testpassword",
            is_recruiter=True,
            company=self.company,
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_list_hr_created_professions_successfully(self):
        HrCreatedProfession.objects.create(
            company=self.company,
            name="Profession 1",
            description="Description 1",
            created_by=self.user,
        )
        HrCreatedProfession.objects.create(
            company=self.company,
            name="Profession 2",
            description="Description 2",
            created_by=self.user,
        )

        url = reverse("hr-created-profession-list-create")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["pagination"]["count"], 2)
        self.assertEqual(len(data["data"]), 2)

    def test_create_hr_created_profession_successfully(self):
        url = reverse("hr-created-profession-list-create")
        data = {
            "company": self.company.id,
            "name": "New Profession",
            "description": "New Description",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        self.assertEqual(response_data["data"]["name"], "New Profession")
        self.assertTrue(
            HrCreatedProfession.objects.filter(name="New Profession").exists()
        )


class HrCreatedProfessionRetrieveUpdateDestroyAPIViewTests(APITestCase):
    """
    Test suite for HrCreatedProfessionRetrieveUpdateDestroyAPIView.
    This includes tests for retrieving, updating, and deleting HR created professions.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.authentication.models import Recruiter
        cls.company = Company.objects.create(name="Test Company", is_active=True)
        cls.user = Recruiter.objects.create_user(
            email="testuser@example.com",
            password="testpassword",
            is_recruiter=True,
            company=cls.company,
            is_staff=True,
        )
        cls.profession = HrCreatedProfession.objects.create(
            company=cls.company,
            name="Existing Profession",
            description="Existing Description",
            created_by=cls.user,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_retrieve_hr_created_profession_successfully(self):
        url = reverse(
            "hr-created-profession-detail", kwargs={"profession_id": self.profession.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["name"], "Existing Profession")
        self.assertEqual(data["description"], "Existing Description")

    def test_update_hr_created_profession_successfully(self):
        url = reverse(
            "hr-created-profession-detail", kwargs={"profession_id": self.profession.id}
        )
        data = {
            "name": "Updated Profession",
            "description": "Updated Description",
            "company": self.company.id,
            "created_by": self.user.id,
        }

        response = self.client.put(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data["data"]["name"], "Updated Profession")

        self.profession.refresh_from_db()
        self.assertEqual(self.profession.name, "Updated Profession")

    def test_delete_hr_created_profession_successfully(self):
        url = reverse(
            "hr-created-profession-detail", kwargs={"profession_id": self.profession.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            HrCreatedProfession.objects.filter(id=self.profession.id).exists()
        )
