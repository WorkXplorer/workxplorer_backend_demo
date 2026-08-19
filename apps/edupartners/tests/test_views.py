import uuid

from django.urls import reverse

from rest_framework.test import APITestCase
from rest_framework import status

from apps.edupartners.models import EduPartner, EduPartnersType


class EduPartnerListAPITests(APITestCase):
    """
    Test suite for the EduPartner List API.

    This endpoint is expected to:
    - Return only active partners
    - Support search by name (case-insensitive)
    - Support filtering by type, country, and city
    - Allow combining search and filters
    """

    @classmethod
    def setUpTestData(cls):
        """
        Create test data:
        - 2 active partners (Harvard, Tashkent School)
        - 1 inactive partner (should not be returned in the API)
        """
        cls.url = reverse("edu-partner-list")

        # Create partner types
        cls.university_type = EduPartnersType.objects.create(name="University")
        cls.school_type = EduPartnersType.objects.create(name="School")

        # Active university partner
        cls.partner1 = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Harvard University",
            edupartner_type=cls.university_type,
            country="USA",
            city="Cambridge",
            is_active=True,
        )
        # Active school partner
        cls.partner2 = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Tashkent School",
            edupartner_type=cls.school_type,
            country="Uzbekistan",
            city="Tashkent",
            is_active=True,
        )
        # Inactive partner (should not appear in results)
        cls.partner_inactive = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Inactive Partner",
            edupartner_type=cls.university_type,
            country="USA",
            city="New York",
            is_active=False,
        )

    def test_list_active_partners(self):
        """
        API should return only active partners.
        Inactive partners must be excluded from the response.
        """
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()["data"]
        names = [p["name"] for p in data]
        assert "Harvard University" in names
        assert "Tashkent School" in names
        assert "Inactive Partner" not in names  # inactive must not appear

    def test_search_by_name(self):
        """
        Searching by name should return relevant partners.
        The search must be case-insensitive.
        """
        response = self.client.get(self.url, {"q": "harvard"})
        assert response.status_code == status.HTTP_200_OK

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["name"] == "Harvard University"

    def test_filter_by_type(self):
        """
        Filtering by type should return only partners of that type.
        """
        response = self.client.get(self.url, {"type": "School"})
        assert response.status_code == status.HTTP_200_OK

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["name"] == "Tashkent School"

    def test_filter_by_country(self):
        """
        Filtering by country should return only partners from that country.
        """
        response = self.client.get(self.url, {"country": "USA"})
        assert response.status_code == status.HTTP_200_OK

        results = response.json()["data"]
        assert all(p["country"] == "USA" for p in results)

    def test_filter_by_city(self):
        """
        Filtering by city should return only partners located in that city.
        """
        response = self.client.get(self.url, {"city": "Tashkent"})
        assert response.status_code == status.HTTP_200_OK

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["city"] == "Tashkent"

    def test_search_and_filter_combined(self):
        """
        API should correctly handle search and filters together.
        """
        response = self.client.get(
            self.url, {"q": "Harvard", "country": "USA", "type": "University"}
        )
        assert response.status_code == status.HTTP_200_OK

        results = response.json()["data"]
        assert len(results) == 1
        assert results[0]["name"] == "Harvard University"

    def test_empty_results(self):
        """
        API should return an empty list if no partners match the filters.
        """
        response = self.client.get(self.url, {"country": "Germany"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == []


class EduPartnersTypeListAPITests(APITestCase):
    """
    Test suite for the EduPartnersType List API.

    This endpoint should:
    - Return all available partner types
    - Order them alphabetically by name
    - Be read-only (only GET requests are allowed)
    - Return the expected response structure (id, name)
    """

    @classmethod
    def setUpTestData(cls):
        """
        Prepare test data:
        - 3 types of educational partners: University, School, College
        """
        cls.url = reverse("edu-partner-types")
        cls.type1 = EduPartnersType.objects.create(name="University")
        cls.type2 = EduPartnersType.objects.create(name="School")
        cls.type3 = EduPartnersType.objects.create(name="College")

    def _get_results(self, response):
        """
        Helper method:
        StandardJSONRenderer wraps responses in {"success": true, "data": ...}
        or {"success": true, "data": ..., "pagination": {...}} for paginated.
        """
        data = response.json()["data"]
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        return data

    def test_list_types_successfully(self):
        """
        API should return all partner types in alphabetical order.
        """
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

        results = self._get_results(response)
        names = [t["name"] for t in results]

        # Ensure alphabetical ordering
        assert names == sorted(names)

        # Ensure all created partner types are included
        assert set(names) == {"University", "School", "College"}

    def test_list_is_readonly(self):
        """
        API must be read-only.
        POST requests should not be allowed.
        Depending on settings, response may return 400, 403, or 405.
        """
        response_post = self.client.post(self.url, {"name": "Institute"})
        assert response_post.status_code in (
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_response_structure(self):
        """
        Each returned type must contain `id` and `name` fields.
        """
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK

        results = self._get_results(response)
        assert all("id" in t and "name" in t for t in results)
