"""
Tests for Language model and LanguageListView API.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from apps.languages.models import Language


class LanguageModelTests(TestCase):
    """Test suite for Language model."""

    def test_create_language(self):
        lang = Language.objects.create(name="English", code="en")
        self.assertEqual(lang.name, "English")
        self.assertEqual(lang.code, "en")
        self.assertIsNotNone(lang.created_at)

    def test_language_str(self):
        lang = Language.objects.create(name="Russian", code="ru")
        self.assertEqual(str(lang), "Russian (ru)")

    def test_unique_name_constraint(self):
        Language.objects.create(name="English", code="en")
        with self.assertRaises(Exception):
            Language.objects.create(name="English", code="en2")

    def test_unique_code_constraint(self):
        Language.objects.create(name="English", code="en")
        with self.assertRaises(Exception):
            Language.objects.create(name="British English", code="en")

    def test_ordering(self):
        Language.objects.create(name="Russian", code="ru")
        Language.objects.create(name="English", code="en")
        Language.objects.create(name="French", code="fr")
        langs = list(Language.objects.values_list("name", flat=True))
        self.assertEqual(langs, ["English", "French", "Russian"])


class LanguageListAPITests(APITestCase):
    """Test suite for Language list API endpoint."""

    def setUp(self):
        self.url = reverse("language-list")
        Language.objects.create(name="English", code="en")
        Language.objects.create(name="Russian", code="ru")
        Language.objects.create(name="Uzbek", code="uz")

    def test_list_languages_unauthenticated(self):
        """Languages list should be accessible without authentication."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_languages_returns_all(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Response may be wrapped in standard envelope due to StandardJSONRenderer
        data = response.data
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        self.assertEqual(len(data), 3)

    def test_list_languages_fields(self):
        response = self.client.get(self.url)
        data = response.data
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        first = data[0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("code", first)

    def test_no_pagination(self):
        """Languages list should not be paginated."""
        response = self.client.get(self.url)
        data = response.data
        # Should not have pagination keys at the top level of raw data
        if isinstance(data, dict) and "data" in data:
            # Wrapped response - data should be a list
            self.assertIsInstance(data["data"], list)
        else:
            self.assertIsInstance(data, list)
