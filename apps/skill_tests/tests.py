from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.skills.models import Skill
from apps.authentication.models import Candidate, Recruiter


class SkillTestAPITests(APITestCase):
    def setUp(self):
        self.generate_url = reverse("skill-test-generate")
        self.candidate = Candidate.objects.create_user(
            email="cand@test.com", password="pass", is_candidate=True,
        )
        self.recruiter = Recruiter.objects.create_user(
            email="rec@test.com", password="pass",
        )

    def test_generate_requires_auth(self):
        response = self.client.post(self.generate_url, {"skill_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_rejects_non_candidate(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.generate_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.skill_tests.views.tests.generate_test")
    def test_generate_invalid_skill(self, mock_gen):
        mock_gen.return_value = {"id": "test-uuid"}
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(
            self.generate_url,
            {"skill_id": 99999, "ai_model": "groq"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("apps.skill_tests.views.tests.generate_test")
    def test_generate_valid_skill(self, mock_gen):
        skill = Skill.objects.create(name="Python")
        mock_gen.return_value = {"id": "test-uuid"}
        self.client.force_authenticate(user=self.candidate)
        response = self.client.post(
            self.generate_url,
            {"skill_id": skill.id, "ai_model": "groq"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)