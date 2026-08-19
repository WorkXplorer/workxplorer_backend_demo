import base64
import hashlib
import json
import time
from unittest.mock import Mock, patch

import jwt
import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from google.auth import exceptions as google_exceptions
from jwt.algorithms import RSAAlgorithm
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Candidate, OAuthChallenge, SocialIdentity
from apps.authentication.services.apple_client import (
    PEM_PRIVATE_KEY_FOOTER,
    PEM_PRIVATE_KEY_HEADER,
    AppleClient,
    AppleNotConfigured,
    AppleUnavailable,
    InvalidAppleToken,
)
from apps.authentication.services import google_verifier
from apps.authentication.services.google_verifier import GoogleUnavailable

MOBILE_KEY = "test-mobile-app-key"
DEVICE = {"device_id": "device-1", "platform": "android"}


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class MobileOAuthChallengeTests(APITestCase):
    def test_challenge_created(self):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "google", "device_id": "device-1"},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        data = response.json()["data"]
        self.assertIn("challenge_id", data)
        self.assertIn("nonce", data)
        self.assertIn("state", data)

    def test_invalid_provider_rejected(self):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "facebook", "device_id": "device-1"},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class MobileGoogleLoginTests(APITestCase):
    def _get_challenge(self, device_id=DEVICE["device_id"]):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "google", "device_id": device_id},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        return response.json()["data"]

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_new_google_user_creates_candidate(self, mock_verify):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "google-sub-1",
            "email": "newgoogle@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }

        response = self.client.post(
            reverse("mobile-google"),
            {"challenge_id": challenge["challenge_id"], "id_token": "fake-token", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertTrue(Candidate.objects.filter(email="newgoogle@example.com").exists())
        self.assertTrue(
            SocialIdentity.objects.filter(provider="google", subject="google-sub-1").exists()
        )
        self.assertIn("access_token", response.json()["data"])

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_returning_google_identity_reuses_account(self, mock_verify):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "google-sub-2",
            "email": "returning@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }
        first = self.client.post(
            reverse("mobile-google"),
            {"challenge_id": challenge["challenge_id"], "id_token": "fake-token", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        # The second sign-in comes from another device, so its challenge has to
        # be issued for that device_id — challenges are bound to one device.
        challenge2 = self._get_challenge(device_id="device-2")
        mock_verify.return_value["nonce"] = challenge2["nonce"]
        second = self.client.post(
            reverse("mobile-google"),
            {"challenge_id": challenge2["challenge_id"], "id_token": "fake-token", "device": {**DEVICE, "device_id": "device-2"}},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK, second.json())
        self.assertEqual(Candidate.objects.filter(email="returning@example.com").count(), 1)

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_wrong_nonce_rejected_as_challenge_invalid(self, mock_verify):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "google-sub-3",
            "email": "x@example.com",
            "email_verified": True,
            "nonce": "not-the-real-nonce",
        }
        response = self.client.post(
            reverse("mobile-google"),
            {"challenge_id": challenge["challenge_id"], "id_token": "fake-token", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"]["code"], "OAUTH_CHALLENGE_INVALID")

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_non_candidate_existing_email_returns_wrong_user_type(self, mock_verify):
        from apps.authentication.models import Company, Recruiter

        company = Company.objects.create(name="Acme", tin="123456789")
        Recruiter.objects.create_user(
            email="recruiter-google@example.com", password="pw", is_recruiter=True, company=company
        )

        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "google-sub-4",
            "email": "recruiter-google@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }
        response = self.client.post(
            reverse("mobile-google"),
            {"challenge_id": challenge["challenge_id"], "id_token": "fake-token", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error"]["code"], "WRONG_USER_TYPE")


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class OAuthChallengeTTLTests(APITestCase):
    def _expires_in(self):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "google", "device_id": "device-1"},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        return response.json()["data"]["expires_in"]

    @override_settings(OAUTH_CHALLENGE_TTL_SECONDS=900)
    def test_expires_in_reports_the_configured_ttl(self):
        self.assertEqual(self._expires_in(), 900)

    @override_settings(OAUTH_CHALLENGE_TTL_SECONDS=1800)
    def test_ttl_is_tunable_without_a_code_change(self):
        self.assertEqual(self._expires_in(), 1800)
        challenge = OAuthChallenge.objects.latest("created_at")
        remaining = (challenge.expires_at - timezone.now()).total_seconds()
        self.assertGreater(remaining, 1700)


class AppleClientConfigTests(TestCase):
    ESCAPED_KEY = "-----BEGIN PRIVATE KEY-----\\nMIGT\\n-----END PRIVATE KEY-----"

    @override_settings(APPLE_PRIVATE_KEY=ESCAPED_KEY)
    def test_literal_newlines_in_the_p8_are_unescaped(self):
        key = AppleClient._normalized_private_key()
        self.assertNotIn("\\n", key)
        self.assertTrue(key.startswith("-----BEGIN PRIVATE KEY-----\n"))
        self.assertTrue(key.endswith("-----END PRIVATE KEY-----"))

    @override_settings(APPLE_PRIVATE_KEY='"  -----BEGIN PRIVATE KEY-----\\nMIGT\\n-----END PRIVATE KEY-----  "')
    def test_surrounding_quotes_and_whitespace_are_stripped(self):
        self.assertTrue(
            AppleClient._normalized_private_key().startswith("-----BEGIN PRIVATE KEY-----")
        )

    @override_settings(APPLE_PRIVATE_KEY="", APPLE_TEAM_ID="TEAM", APPLE_KEY_ID="KEY")
    @patch("apps.authentication.services.apple_client.AppleClient._cache_get", return_value=None)
    def test_missing_private_key_raises_not_configured(self, _cache_get):
        with self.assertRaises(AppleNotConfigured):
            AppleClient._generate_client_secret()

    @override_settings(
        APPLE_PRIVATE_KEY="not-a-pem", APPLE_TEAM_ID="TEAM", APPLE_KEY_ID="KEY", APPLE_CLIENT_ID="app"
    )
    @patch("apps.authentication.services.apple_client.AppleClient._cache_set")
    @patch("apps.authentication.services.apple_client.AppleClient._cache_get", return_value=None)
    def test_unusable_private_key_raises_not_configured(self, _cache_get, _cache_set):
        with self.assertRaises(AppleNotConfigured):
            AppleClient._generate_client_secret()

    @patch("apps.authentication.services.apple_client.AppleClient._cache_set")
    @patch("apps.authentication.services.apple_client.AppleClient._cache_get", return_value=None)
    @patch("apps.authentication.services.apple_client.requests.get")
    def test_unreachable_jwks_raises_unavailable(self, mock_get, _cache_get, _cache_set):
        mock_get.side_effect = requests.ConnectionError("boom")
        with self.assertRaises(AppleUnavailable):
            AppleClient._get_jwks()

    @patch("apps.authentication.services.apple_client.AppleClient._get_jwks", return_value={"keys": []})
    def test_identity_token_without_kid_is_invalid_not_a_crash(self, _jwks):
        token = jwt.encode({"sub": "x"}, "secret", algorithm="HS256")
        with override_settings(APPLE_CLIENT_ID="com.workxplorer.app"):
            with self.assertRaises(InvalidAppleToken):
                AppleClient.verify_identity_token(token)


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class MobileAppleLoginTests(APITestCase):
    IOS_DEVICE = {"device_id": "ios-device-1", "platform": "ios"}

    def _get_challenge(self):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "apple", "device_id": self.IOS_DEVICE["device_id"]},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        return response.json()["data"]

    def _post(self, challenge):
        return self.client.post(
            reverse("mobile-apple"),
            {
                "challenge_id": challenge["challenge_id"],
                "state": challenge["state"],
                "identity_token": "fake-identity-token",
                "authorization_code": "fake-code",
                "device": self.IOS_DEVICE,
            },
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )

    @patch("apps.authentication.views.mobile_oauth.AppleClient.exchange_authorization_code")
    @patch("apps.authentication.views.mobile_oauth.AppleClient.verify_identity_token")
    @override_settings(AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    def test_new_apple_user_creates_candidate(self, mock_verify, mock_exchange):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "apple-sub-1",
            "email": "newapple@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }
        mock_exchange.return_value = {"refresh_token": "apple-refresh"}

        response = self._post(challenge)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertTrue(Candidate.objects.filter(email="newapple@example.com").exists())
        identity = SocialIdentity.objects.get(provider="apple", subject="apple-sub-1")
        self.assertTrue(identity.apple_refresh_token_ciphertext)

    @patch("apps.authentication.views.mobile_oauth.AppleClient.verify_identity_token")
    def test_missing_apple_config_returns_503_not_500(self, mock_verify):
        mock_verify.side_effect = AppleNotConfigured("APPLE_PRIVATE_KEY")
        response = self._post(self._get_challenge())
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())
        self.assertEqual(response.json()["error"]["code"], "APPLE_NOT_CONFIGURED")

    @patch("apps.authentication.views.mobile_oauth.AppleClient.verify_identity_token")
    def test_unreachable_apple_returns_503_not_500(self, mock_verify):
        mock_verify.side_effect = AppleUnavailable()
        response = self._post(self._get_challenge())
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())
        self.assertEqual(response.json()["error"]["code"], "APPLE_UNAVAILABLE")

    @patch("apps.authentication.views.mobile_oauth.AppleClient.exchange_authorization_code")
    @patch("apps.authentication.views.mobile_oauth.AppleClient.verify_identity_token")
    def test_code_exchange_config_failure_returns_503_not_500(self, mock_verify, mock_exchange):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "apple-sub-2",
            "email": "apple2@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }
        mock_exchange.side_effect = AppleNotConfigured("APPLE_PRIVATE_KEY")

        response = self._post(challenge)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())
        self.assertEqual(response.json()["error"]["code"], "APPLE_NOT_CONFIGURED")

    @patch("apps.authentication.views.mobile_oauth.AppleClient.exchange_authorization_code")
    @patch("apps.authentication.views.mobile_oauth.AppleClient.verify_identity_token")
    @override_settings(AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY="")
    def test_unset_encryption_key_returns_503_not_500(self, mock_verify, mock_exchange):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "apple-sub-3",
            "email": "apple3@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }
        mock_exchange.return_value = {"refresh_token": "apple-refresh"}

        response = self._post(challenge)
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())
        self.assertEqual(response.json()["error"]["code"], "APPLE_NOT_CONFIGURED")


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class MobileGoogleFailureModeTests(APITestCase):
    def _get_challenge(self):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "google", "device_id": DEVICE["device_id"]},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        return response.json()["data"]

    def _post(self, challenge):
        return self.client.post(
            reverse("mobile-google"),
            {"challenge_id": challenge["challenge_id"], "id_token": "fake-token", "device": DEVICE},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_unreachable_google_returns_503_not_500(self, mock_verify):
        mock_verify.side_effect = GoogleUnavailable()
        response = self._post(self._get_challenge())
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())
        self.assertEqual(response.json()["error"]["code"], "GOOGLE_UNAVAILABLE")

    @patch("apps.authentication.services.google_verifier.id_token.verify_oauth2_token")
    def test_certs_transport_error_is_not_a_500(self, mock_verify):
        mock_verify.side_effect = google_exceptions.TransportError("connection timed out")
        response = self._post(self._get_challenge())
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())

    @patch("apps.authentication.services.google_verifier.id_token.verify_oauth2_token")
    def test_token_without_email_claim_is_rejected_not_a_500(self, mock_verify):
        mock_verify.return_value = {"sub": "google-sub-9", "email_verified": True}
        response = self._post(self._get_challenge())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.json())
        self.assertEqual(response.json()["error"]["code"], "INVALID_GOOGLE_TOKEN")

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_hashed_nonce_from_the_sdk_is_accepted(self, mock_verify):
        # Apple's documented flow (and several RN wrappers) send SHA256(rawNonce)
        # to the provider, so the token echoes the hash, not the raw value.
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "google-sub-hashed",
            "email": "hashed@example.com",
            "email_verified": True,
            "nonce": hashlib.sha256(challenge["nonce"].encode()).hexdigest(),
        }
        response = self._post(challenge)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())

    @patch("apps.authentication.views.mobile_oauth.verify_google_id_token")
    def test_rejection_reason_is_logged(self, mock_verify):
        challenge = self._get_challenge()
        mock_verify.return_value = {
            "subject": "google-sub-10",
            "email": "y@example.com",
            "email_verified": True,
            "nonce": challenge["nonce"],
        }
        with self.assertLogs("apps.authentication.views.mobile_oauth", level="WARNING") as logs:
            response = self.client.post(
                reverse("mobile-google"),
                {
                    "challenge_id": challenge["challenge_id"],
                    "id_token": "fake-token",
                    # Challenge was issued for device-1; sign in from another device.
                    "device": {**DEVICE, "device_id": "some-other-device"},
                },
                format="json",
                HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("device_id_mismatch", "\n".join(logs.output))


@override_settings(MOBILE_APP_API_KEY=MOBILE_KEY)
class MobileAppleEndToEndTests(APITestCase):
    """
    Drives /auth/mobile/apple/ with a locally minted identity token verified
    through the real code path — real JWKS lookup, real RS256 verification,
    real challenge consumption, real ES256 client_secret signing, real Fernet
    encryption. Only Apple's two HTTP endpoints are stubbed, so this covers
    everything an iOS device would exercise except Apple's own signature.
    """

    IOS_DEVICE = {"device_id": "ios-e2e", "platform": "ios"}
    CLIENT_ID = "com.workxplorer.app"
    KID = "test-apple-kid"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(cls.rsa_key.public_key()))
        jwk["kid"] = cls.KID
        cls.jwks = {"keys": [jwk]}
        cls.rsa_pem = cls.rsa_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        # Stands in for the .p8 from the Apple developer portal (same ES256 curve).
        cls.p8 = (
            ec.generate_private_key(ec.SECP256R1())
            .private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            .decode()
        )

    def _identity_token(self, *, subject, email, nonce, audience=None):
        now = int(time.time())
        return jwt.encode(
            {
                "iss": "https://appleid.apple.com",
                "aud": audience or self.CLIENT_ID,
                "sub": subject,
                "email": email,
                "email_verified": "true",
                "nonce": nonce,
                "iat": now,
                "exp": now + 600,
            },
            self.rsa_pem,
            algorithm="RS256",
            headers={"kid": self.KID},
        )

    def _get_challenge(self):
        response = self.client.post(
            reverse("mobile-oauth-challenge"),
            {"provider": "apple", "device_id": self.IOS_DEVICE["device_id"]},
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )
        return response.json()["data"]

    def _apple_token_response(self, subject):
        response = Mock()
        response.ok = True
        response.json.return_value = {
            "refresh_token": "apple-refresh-token",
            "id_token": jwt.encode({"sub": subject}, "irrelevant", algorithm="HS256"),
        }
        return response

    def _sign_in(self, *, subject, email, nonce_transform=lambda n: n):
        challenge = self._get_challenge()
        return self.client.post(
            reverse("mobile-apple"),
            {
                "challenge_id": challenge["challenge_id"],
                "state": challenge["state"],
                "identity_token": self._identity_token(
                    subject=subject, email=email, nonce=nonce_transform(challenge["nonce"])
                ),
                "authorization_code": "apple-authorization-code",
                "device": self.IOS_DEVICE,
            },
            format="json",
            HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
        )

    def _settings(self, **overrides):
        base = {
            "APPLE_CLIENT_ID": self.CLIENT_ID,
            "APPLE_TEAM_ID": "TEAMID1234",
            "APPLE_KEY_ID": "KEYID12345",
            "APPLE_PRIVATE_KEY": self.p8,
            "AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "MOBILE_APP_API_KEY": MOBILE_KEY,
        }
        base.update(overrides)
        return override_settings(**base)

    def test_full_apple_login_succeeds_against_a_minted_token(self):
        with self._settings(), patch.object(AppleClient, "_get_jwks", return_value=self.jwks), patch.object(
            AppleClient, "_cache_get", return_value=None
        ), patch.object(AppleClient, "_cache_set"), patch(
            "apps.authentication.services.apple_client.requests.post"
        ) as mock_post:
            mock_post.return_value = self._apple_token_response("apple-e2e-sub")
            response = self._sign_in(subject="apple-e2e-sub", email="e2e@example.com")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertTrue(Candidate.objects.filter(email="e2e@example.com").exists())
        identity = SocialIdentity.objects.get(provider="apple", subject="apple-e2e-sub")
        self.assertTrue(identity.apple_refresh_token_ciphertext)
        self.assertIn("access_token", response.json()["data"])

        # The client_secret Apple was sent is a real ES256 JWT for our team/key.
        sent_secret = mock_post.call_args.kwargs["data"]["client_secret"]
        header = jwt.get_unverified_header(sent_secret)
        self.assertEqual(header["alg"], "ES256")
        self.assertEqual(header["kid"], "KEYID12345")
        claims = jwt.decode(sent_secret, options={"verify_signature": False}, audience="https://appleid.apple.com")
        self.assertEqual(claims["iss"], "TEAMID1234")
        self.assertEqual(claims["sub"], self.CLIENT_ID)

    def test_full_apple_login_accepts_a_hashed_nonce(self):
        with self._settings(), patch.object(AppleClient, "_get_jwks", return_value=self.jwks), patch.object(
            AppleClient, "_cache_get", return_value=None
        ), patch.object(AppleClient, "_cache_set"), patch(
            "apps.authentication.services.apple_client.requests.post"
        ) as mock_post:
            mock_post.return_value = self._apple_token_response("apple-hashed-sub")
            response = self._sign_in(
                subject="apple-hashed-sub",
                email="hashed-apple@example.com",
                nonce_transform=lambda n: hashlib.sha256(n.encode()).hexdigest(),
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())

    def test_token_minted_for_another_audience_is_rejected(self):
        with self._settings(), patch.object(AppleClient, "_get_jwks", return_value=self.jwks), patch.object(
            AppleClient, "_cache_get", return_value=None
        ), patch.object(AppleClient, "_cache_set"):
            challenge = self._get_challenge()
            response = self.client.post(
                reverse("mobile-apple"),
                {
                    "challenge_id": challenge["challenge_id"],
                    "state": challenge["state"],
                    "identity_token": self._identity_token(
                        subject="s", email="e@example.com", nonce=challenge["nonce"], audience="com.someone.else"
                    ),
                    "authorization_code": "code",
                    "device": self.IOS_DEVICE,
                },
                format="json",
                HTTP_X_MOBILE_APP_KEY=MOBILE_KEY,
            )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.json())
        self.assertEqual(response.json()["error"]["code"], "INVALID_APPLE_TOKEN")

    def test_unusable_p8_is_the_503_seen_in_production(self):
        with self._settings(APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\\nbroken\\n-----END PRIVATE KEY-----"), patch.object(
            AppleClient, "_get_jwks", return_value=self.jwks
        ), patch.object(AppleClient, "_cache_get", return_value=None), patch.object(AppleClient, "_cache_set"):
            response = self._sign_in(subject="apple-broken-key", email="broken@example.com")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE, response.json())
        self.assertEqual(response.json()["error"]["code"], "APPLE_NOT_CONFIGURED")


class ApplePrivateKeyShapeTests(TestCase):
    """
    Every shape a secret store might hold the .p8 in must end up signing a
    real client_secret — the production failure was a value stored without
    the PEM armor, which cryptography rejects as MalformedFraming.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pem = (
            ec.generate_private_key(ec.SECP256R1())
            .private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            .decode()
            .strip()
        )
        body = "".join(cls.pem.splitlines()[1:-1])
        cls.shapes = {
            "pem": cls.pem,
            "escaped_newlines": cls.pem.replace("\n", "\\n"),
            "quoted_escaped_newlines": '"' + cls.pem.replace("\n", "\\n") + '"',
            "base64_of_whole_file": base64.b64encode(cls.pem.encode()).decode(),
            "bare_body_no_armor": body,
            "bare_body_wrapped": "\n".join(body[i:i + 64] for i in range(0, len(body), 64)),
            "armored_but_flattened": f"{PEM_PRIVATE_KEY_HEADER} {body} {PEM_PRIVATE_KEY_FOOTER}",
        }

    def test_every_stored_shape_normalizes_to_the_same_pem(self):
        for name, stored in self.shapes.items():
            with self.subTest(shape=name), override_settings(APPLE_PRIVATE_KEY=stored):
                self.assertEqual(AppleClient._normalized_private_key(), self.pem)

    def test_every_stored_shape_signs_a_client_secret(self):
        for name, stored in self.shapes.items():
            with self.subTest(shape=name), override_settings(
                APPLE_PRIVATE_KEY=stored,
                APPLE_TEAM_ID="TEAMID1234",
                APPLE_KEY_ID="KEYID12345",
                APPLE_CLIENT_ID="com.workxplorer.app",
            ), patch.object(AppleClient, "_cache_get", return_value=None), patch.object(
                AppleClient, "_cache_set"
            ):
                secret = AppleClient._generate_client_secret()
                self.assertEqual(jwt.get_unverified_header(secret)["alg"], "ES256")

    @override_settings(APPLE_PRIVATE_KEY="clearly not a key at all !!!")
    def test_unrecoverable_value_is_left_alone_to_fail_loudly(self):
        self.assertEqual(AppleClient._normalized_private_key(), "clearly not a key at all !!!")


class GoogleCertsCacheTests(TestCase):
    """
    google-auth refetches Google's signing certs on every verification, which
    puts an outbound round-trip on the critical path of each login — the app
    times out long before the library's own 120s does. These pin the caching
    that removes it.
    """

    CERTS = {"kid-1": "-----BEGIN CERTIFICATE-----\nnot-a-real-cert\n-----END CERTIFICATE-----"}

    def setUp(self):
        self.store = {}
        patcher_get = patch(
            "apps.authentication.services.google_verifier.cache_get",
            side_effect=lambda key: self.store.get(key),
        )
        patcher_set = patch(
            "apps.authentication.services.google_verifier.cache_set",
            side_effect=lambda key, ttl, value: self.store.__setitem__(key, value),
        )
        patcher_del = patch(
            "apps.authentication.services.google_verifier.cache_delete",
            side_effect=lambda key: self.store.pop(key, None),
        )
        for patcher in (patcher_get, patcher_set, patcher_del):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _fake_upstream(self):
        """Stands in for google_requests.Request.__call__ (the real network hop)."""
        response = Mock()
        response.status = 200
        response.data = json.dumps(self.CERTS).encode()
        response.headers = {"cache-control": "public, max-age=7200"}
        return response

    def test_certs_are_fetched_once_then_served_from_cache(self):
        request = google_verifier._CachedCertsRequest()
        with patch.object(
            google_verifier.google_requests.Request, "__call__", return_value=self._fake_upstream()
        ) as upstream:
            first = request(google_verifier.GOOGLE_CERTS_URL)
            second = request(google_verifier.GOOGLE_CERTS_URL)
            third = request(google_verifier.GOOGLE_CERTS_URL)

        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(json.loads(second.data), self.CERTS)
        self.assertEqual(first.data, third.data)

    def test_cache_lifetime_follows_google_cache_control(self):
        captured = {}
        with patch(
            "apps.authentication.services.google_verifier.cache_set",
            side_effect=lambda key, ttl, value: captured.update(ttl=ttl),
        ), patch.object(
            google_verifier.google_requests.Request, "__call__", return_value=self._fake_upstream()
        ):
            google_verifier._CachedCertsRequest()(google_verifier.GOOGLE_CERTS_URL)
        self.assertEqual(captured["ttl"], 7200)

    def test_certs_fetch_gets_a_bounded_timeout(self):
        with patch.object(
            google_verifier.google_requests.Request, "__call__", return_value=self._fake_upstream()
        ) as upstream:
            google_verifier._CachedCertsRequest()(google_verifier.GOOGLE_CERTS_URL)
        passed_timeout = upstream.call_args.args[4]
        self.assertEqual(passed_timeout, google_verifier.CERTS_FETCH_TIMEOUT_SECONDS)

    def test_other_urls_are_not_intercepted(self):
        with patch.object(
            google_verifier.google_requests.Request, "__call__", return_value=self._fake_upstream()
        ) as upstream:
            google_verifier._CachedCertsRequest()("https://example.com/other")
            google_verifier._CachedCertsRequest()("https://example.com/other")
        self.assertEqual(upstream.call_count, 2)
        self.assertNotIn(google_verifier.CERTS_CACHE_KEY, self.store)

    def test_a_token_signed_by_an_unknown_key_drops_the_cache(self):
        self.store[google_verifier.CERTS_CACHE_KEY] = json.dumps(self.CERTS).encode()
        rotated = jwt.encode({"sub": "x"}, "secret", algorithm="HS256", headers={"kid": "kid-99"})

        google_verifier._refresh_certs_if_key_is_unknown(rotated)

        self.assertNotIn(google_verifier.CERTS_CACHE_KEY, self.store)

    def test_a_known_key_keeps_the_cache(self):
        self.store[google_verifier.CERTS_CACHE_KEY] = json.dumps(self.CERTS).encode()
        known = jwt.encode({"sub": "x"}, "secret", algorithm="HS256", headers={"kid": "kid-1"})

        google_verifier._refresh_certs_if_key_is_unknown(known)

        self.assertIn(google_verifier.CERTS_CACHE_KEY, self.store)

    def test_a_dead_cache_still_verifies(self):
        with patch(
            "apps.authentication.services.google_verifier.cache_get", return_value=None
        ), patch(
            "apps.authentication.services.google_verifier.cache_set"
        ), patch.object(
            google_verifier.google_requests.Request, "__call__", return_value=self._fake_upstream()
        ) as upstream:
            response = google_verifier._CachedCertsRequest()(google_verifier.GOOGLE_CERTS_URL)
        self.assertEqual(upstream.call_count, 1)
        self.assertEqual(json.loads(response.data), self.CERTS)
