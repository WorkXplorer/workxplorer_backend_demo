from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import CustomUser


class AIActionAPITests(APITestCase):
    def setUp(self):
        self.url = reverse("ai-validate")
        self.staff = CustomUser.objects.create_user(
            email="staff@test.com", password="pass123", is_staff=True,
        )

    def test_requires_authentication(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_requires_status_param(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.ai.views.ai_action.validate_passive_skills")
    def test_post_validates_status(self, mock_validate):
        mock_validate.return_value = {"validated": 0}
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            self.url, {"status": "passive_skills", "ai_model": "default"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
