from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate, MobileSession

MOBILE_KEY = "test-mobile-app-key"
DEVICE = {"device_id": "device-1", "platform": "ios", "app_version": "1.0.0"}


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class MobileAuthTests(APITestCase):
    def setUp(self):
        self.login_url = reverse("mobile-login")
        self.refresh_url = reverse("mobile-refresh")
        self.logout_url = reverse("mobile-logout")
        self.logout_all_url = reverse("mobile-logout-all")
        self.candidate = Candidate.objects.create_user(
            email="mobile-candidate@example.com",
            password="testpass123",
            is_candidate=True,
        )

    def _login(self, device_id="device-1"):
        return self.client.post(
            self.login_url,
            {
                "email": "mobile-candidate@example.com",
                "password": "testpass123",
                "device": {**DEVICE, "device_id": device_id},
            },
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )

    def test_login_without_mobile_key_is_rejected(self):
        response = self.client.post(
            self.login_url,
            {"email": "mobile-candidate@example.com", "password": "testpass123", "device": DEVICE},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(MOBILE_APP_API_KEY=None)
    def test_login_with_unset_mobile_key_fails_closed(self):
        response = self.client.post(
            self.login_url,
            {"email": "mobile-candidate@example.com", "password": "testpass123", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_candidate_is_rejected(self):
        from apps.authentication.models import Recruiter, Company

        company = Company.objects.create(name="Acme", tin="123456789")
        Recruiter.objects.create_user(
            email="recruiter@example.com", password="testpass123", is_recruiter=True, company=company
        )
        response = self.client.post(
            self.login_url,
            {"email": "recruiter@example.com", "password": "testpass123", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error"]["code"], "WRONG_USER_TYPE")

    def test_login_returns_opaque_tokens_in_body_not_cookies(self):
        response = self._login()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertIn("session_id", data)
        self.assertNotIn("access_token", response.cookies)
        self.assertNotIn("refresh_token", response.cookies)
        self.assertEqual(MobileSession.objects.filter(user=self.candidate).count(), 1)

    def test_access_token_authorizes_protected_endpoint_via_header(self):
        login_response = self._login()
        access_token = login_response.json()["data"]["access_token"]

        response = self.client.patch(
            reverse("update-language"),
            {"preferred_language": "en"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())

    def test_refresh_without_mobile_key_rejected(self):
        login_response = self._login()
        refresh_token = login_response.json()["data"]["refresh_token"]

        response = self.client.post(self.refresh_url, {"refresh_token": refresh_token}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_refresh_returns_new_token_pair_and_rotates(self):
        login_response = self._login()
        old_refresh = login_response.json()["data"]["refresh_token"]

        response = self.client.post(
            self.refresh_url, {"refresh_token": old_refresh}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        data = response.json()["data"]
        self.assertIn("access_token", data)
        self.assertNotEqual(data["refresh_token"], old_refresh)

    def test_refresh_with_invalid_token_is_rejected(self):
        response = self.client.post(
            self.refresh_url, {"refresh_token": "not-a-real-token"}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REFRESH_TOKEN")

    def test_replayed_refresh_token_revokes_session(self):
        login_response = self._login()
        old_refresh = login_response.json()["data"]["refresh_token"]

        first = self.client.post(
            self.refresh_url, {"refresh_token": old_refresh}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        # Reusing the now-rotated-away token is a replay.
        replay = self.client.post(
            self.refresh_url, {"refresh_token": old_refresh}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(replay.json()["error"]["code"], "REFRESH_TOKEN_REUSED")

        # And the session is now fully dead, even for the newest (valid) token.
        new_refresh = first.json()["data"]["refresh_token"]
        after = self.client.post(
            self.refresh_url, {"refresh_token": new_refresh}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(after.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(after.json()["error"]["code"], "SESSION_REVOKED")

    def test_logout_revokes_only_current_device(self):
        session_a = self._login(device_id="device-a")
        session_b = self._login(device_id="device-b")
        refresh_a = session_a.json()["data"]["refresh_token"]
        refresh_b = session_b.json()["data"]["refresh_token"]

        logout_response = self.client.post(
            self.logout_url, {"refresh_token": refresh_a}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(logout_response.status_code, status.HTTP_204_NO_CONTENT)

        # device A's session is dead
        refresh_a_again = self.client.post(
            self.refresh_url, {"refresh_token": refresh_a}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(refresh_a_again.status_code, status.HTTP_401_UNAUTHORIZED)

        # device B is untouched
        refresh_b_again = self.client.post(
            self.refresh_url, {"refresh_token": refresh_b}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(refresh_b_again.status_code, status.HTTP_200_OK)

    def test_logout_is_idempotent_for_unknown_token(self):
        response = self.client.post(
            self.logout_url, {"refresh_token": "unknown"}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_logout_all_revokes_every_device(self):
        session_a = self._login(device_id="device-a")
        session_b = self._login(device_id="device-b")
        access_a = session_a.json()["data"]["access_token"]
        refresh_b = session_b.json()["data"]["refresh_token"]

        response = self.client.post(
            self.logout_all_url,
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access_a}",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        refresh_b_again = self.client.post(
            self.refresh_url, {"refresh_token": refresh_b}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(refresh_b_again.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_all_requires_bearer_token(self):
        response = self.client.post(
            self.logout_all_url, {}, format="json", HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_revoked_session_access_token_rejected_immediately(self):
        """sid-based check in CookieJWTAuthentication should reject an access
        token from a session logout-all just revoked, even though the JWT
        itself hasn't naturally expired yet."""
        login_response = self._login()
        access_token = login_response.json()["data"]["access_token"]

        self.client.post(
            self.logout_all_url,
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )

        response = self.client.patch(
            reverse("update-language"),
            {"preferred_language": "en"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
