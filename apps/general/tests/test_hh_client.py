from django.test import override_settings
from rest_framework.test import APITestCase
from unittest.mock import Mock, patch

from apps.general.services import hh_client


class HHClientTests(APITestCase):
    @override_settings(
        HH_ACCESS_TOKEN="test-token",
        HH_API_BASE_URL="https://api.hh.test",
        HH_USER_AGENT="WorkXplorerTest/1.0",
    )
    @patch("apps.general.services.hh_client.requests.get")
    def test_request_sends_application_authorization(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}
        mock_get.return_value = mock_response

        data = hh_client.request_hh_json(
            "/vacancies",
            params={"text": "python"},
        )

        self.assertEqual(data, {"items": []})
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(kwargs["headers"]["HH-User-Agent"], "WorkXplorerTest/1.0")
        self.assertEqual(kwargs["headers"]["User-Agent"], "WorkXplorerTest/1.0")
        self.assertEqual(kwargs["headers"]["Accept"], "application/json")
        self.assertEqual(kwargs["timeout"], 7)

    @override_settings(HH_ACCESS_TOKEN="")
    def test_request_requires_access_token(self):
        with self.assertRaises(hh_client.HHConfigurationError) as error:
            hh_client.request_hh_json("/vacancies")

        self.assertIn("HH_ACCESS_TOKEN", str(error.exception))

    @override_settings(
        HH_ACCESS_TOKEN="",
        HH_CLIENT_ID="client-id",
        HH_CLIENT_SECRET="client-secret",
        HH_TOKEN_URL="https://hh.test/oauth/token",
    )
    @patch("apps.general.services.hh_client.requests.post")
    @patch("apps.general.services.hh_client.requests.get")
    def test_request_fetches_token_from_client_credentials(
        self,
        mock_get,
        mock_post,
    ):
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "generated-token"}
        mock_post.return_value = token_response

        vacancy_response = Mock()
        vacancy_response.status_code = 200
        vacancy_response.json.return_value = {"items": []}
        mock_get.return_value = vacancy_response

        data = hh_client.request_hh_json("/vacancies")

        self.assertEqual(data, {"items": []})
        mock_post.assert_called_once()
        _, token_kwargs = mock_post.call_args
        self.assertEqual(token_kwargs["data"]["grant_type"], "client_credentials")
        self.assertEqual(token_kwargs["data"]["client_id"], "client-id")
        self.assertEqual(token_kwargs["data"]["client_secret"], "client-secret")

        _, vacancy_kwargs = mock_get.call_args
        self.assertEqual(
            vacancy_kwargs["headers"]["Authorization"],
            "Bearer generated-token",
        )
