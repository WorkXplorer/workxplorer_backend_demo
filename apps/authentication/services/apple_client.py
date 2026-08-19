import base64
import binascii
import json
import logging
import time

import jwt
import requests
from django.conf import settings
from jwt.algorithms import RSAAlgorithm
from redis import Redis

from apps.authentication.services import provider_cache

logger = logging.getLogger(__name__)

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"

PEM_PRIVATE_KEY_HEADER = "-----BEGIN PRIVATE KEY-----"
PEM_PRIVATE_KEY_FOOTER = "-----END PRIVATE KEY-----"


class InvalidAppleToken(Exception):
    pass


class InvalidAppleCode(Exception):
    pass


class AppleNotConfigured(Exception):
    """A required APPLE_* setting is missing or unusable (bad .p8, etc.)."""


class AppleUnavailable(Exception):
    """Apple's own endpoints (JWKS) couldn't be reached — transient, not the caller's fault."""


class AppleClient:
    JWKS_CACHE_KEY = "apple:jwks"
    JWKS_CACHE_TTL_SECONDS = 24 * 60 * 60
    CLIENT_SECRET_CACHE_KEY = "apple:client_secret"
    CLIENT_SECRET_TTL_SECONDS = 15 * 60

    @classmethod
    def _get_redis_connection(cls) -> Redis:
        return provider_cache.get_redis()

    @classmethod
    def _cache_get(cls, key: str):
        """Cache reads are best-effort — a broken/absent Redis must never 500 a login."""
        return provider_cache.cache_get(key)

    @classmethod
    def _cache_set(cls, key: str, ttl: int, value) -> None:
        provider_cache.cache_set(key, ttl, value)

    @classmethod
    def _fetch_jwks(cls) -> dict:
        try:
            response = requests.get(APPLE_JWKS_URL, timeout=10)
            response.raise_for_status()
            jwks = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("Apple: JWKS fetch failed: %s", exc)
            raise AppleUnavailable() from exc

        cls._cache_set(cls.JWKS_CACHE_KEY, cls.JWKS_CACHE_TTL_SECONDS, json.dumps(jwks))
        return jwks

    @classmethod
    def _get_jwks(cls, force_refresh: bool = False) -> dict:
        if not force_refresh:
            cached = cls._cache_get(cls.JWKS_CACHE_KEY)
            if cached:
                try:
                    return json.loads(cached)
                except ValueError:
                    logger.warning("Apple: cached JWKS was not valid JSON, refetching.")

        return cls._fetch_jwks()

    @classmethod
    def _get_signing_key(cls, kid: str):
        jwks = cls._get_jwks()
        jwk = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if jwk is None:
            # Unknown kid — one controlled refresh, in case Apple rotated keys.
            jwks = cls._get_jwks(force_refresh=True)
            jwk = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

        if jwk is None:
            raise InvalidAppleToken()

        return RSAAlgorithm.from_jwk(json.dumps(jwk))

    @classmethod
    def verify_identity_token(cls, identity_token: str) -> dict:
        """
        Verifies signature (via Apple's JWKS, fixed URL — never built from
        the token's own kid path), iss, aud, exp. Returns {"subject",
        "email", "email_verified", "nonce"} — email/email_verified are only
        present on first consent, per Apple. Caller matches "nonce" against
        the OAuthChallenge it consumed for this request.
        """
        if not settings.APPLE_CLIENT_ID:
            logger.error("Apple: APPLE_CLIENT_ID is not set — cannot verify the identity token.")
            raise AppleNotConfigured("APPLE_CLIENT_ID")

        try:
            unverified_header = jwt.get_unverified_header(identity_token)
        except jwt.PyJWTError as exc:
            logger.warning("Apple identity token has an unreadable header: %s", exc)
            raise InvalidAppleToken() from exc

        kid = unverified_header.get("kid")
        if not kid:
            logger.warning("Apple identity token header carries no kid.")
            raise InvalidAppleToken()

        try:
            signing_key = cls._get_signing_key(kid)

            claims = jwt.decode(
                identity_token,
                key=signing_key,
                algorithms=["RS256"],
                audience=settings.APPLE_CLIENT_ID,
                issuer=APPLE_ISSUER,
            )
        except jwt.PyJWTError as exc:
            logger.warning("Apple identity token verification failed: %s", exc)
            raise InvalidAppleToken() from exc

        if not claims.get("sub"):
            logger.warning("Apple identity token carries no sub claim.")
            raise InvalidAppleToken()

        return {
            "subject": claims["sub"],
            "email": claims.get("email"),
            "email_verified": str(claims.get("email_verified", "false")).lower() == "true",
            "nonce": claims.get("nonce"),
        }

    @classmethod
    def _normalized_private_key(cls) -> str:
        """
        The .p8 is a multi-line PEM, and every secret store mangles it
        differently. `cryptography` accepts exactly one shape, so recover the
        four that show up in practice:

        * real newlines (already fine),
        * literal backslash-n, optionally wrapped in quotes,
        * the whole file base64-encoded (`base64 -w0 AuthKey.p8`),
        * just the key body, with the BEGIN/END armor stripped off.

        Anything else is returned untouched so it fails loudly at signing time
        rather than being silently guessed at.
        """
        raw = settings.APPLE_PRIVATE_KEY or ""
        key = raw.strip().strip('"').strip("'").strip()
        if "\\n" in key:
            key = key.replace("\\n", "\n").strip()

        if not key:
            return key

        if PEM_PRIVATE_KEY_HEADER in key:
            if "\n" in key:
                return key
            # Armored, but flattened onto one line (newlines eaten somewhere in
            # transit) — rebuild it from the body between the markers.
            body = key.split(PEM_PRIVATE_KEY_HEADER, 1)[1].split(PEM_PRIVATE_KEY_FOOTER, 1)[0]
            return cls._rearmor_pem_body(body) or key

        recovered = cls._decode_base64_pem(key) or cls._rearmor_pem_body(key)
        if recovered:
            logger.warning(
                "Apple: APPLE_PRIVATE_KEY is not stored as a PEM — recovered it, but store the "
                "full .p8 contents (BEGIN/END lines included) to avoid relying on this."
            )
            return recovered

        return key

    @staticmethod
    def _decode_base64_pem(value: str) -> str | None:
        """The whole .p8 base64-encoded once more — decode back to the PEM text."""
        try:
            decoded = base64.b64decode(value, validate=False).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return None
        decoded = decoded.strip()
        return decoded if PEM_PRIVATE_KEY_HEADER in decoded else None

    @staticmethod
    def _rearmor_pem_body(value: str) -> str | None:
        """Bare base64 key body with the armor stripped — put the PEM back around it."""
        body = "".join(value.split())
        try:
            base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError):
            return None

        lines = [body[i:i + 64] for i in range(0, len(body), 64)]
        return "\n".join([PEM_PRIVATE_KEY_HEADER, *lines, PEM_PRIVATE_KEY_FOOTER])

    @classmethod
    def _generate_client_secret(cls, force_refresh: bool = False) -> str:
        if not force_refresh:
            cached = cls._cache_get(cls.CLIENT_SECRET_CACHE_KEY)
            if cached:
                return cached.decode("utf-8")

        private_key = cls._normalized_private_key()
        missing = [
            name
            for name, value in (
                ("APPLE_TEAM_ID", settings.APPLE_TEAM_ID),
                ("APPLE_CLIENT_ID", settings.APPLE_CLIENT_ID),
                ("APPLE_KEY_ID", settings.APPLE_KEY_ID),
                ("APPLE_PRIVATE_KEY", private_key),
            )
            if not value
        ]
        if missing:
            logger.error("Apple: cannot build client_secret, unset settings: %s", ", ".join(missing))
            raise AppleNotConfigured(", ".join(missing))

        now = int(time.time())
        payload = {
            "iss": settings.APPLE_TEAM_ID,
            "sub": settings.APPLE_CLIENT_ID,
            "aud": APPLE_ISSUER,
            "iat": now,
            "exp": now + cls.CLIENT_SECRET_TTL_SECONDS,
        }
        try:
            client_secret = jwt.encode(
                payload,
                private_key,
                algorithm="ES256",
                headers={"kid": settings.APPLE_KEY_ID},
            )
        except Exception as exc:
            # A malformed/wrong-type .p8 surfaces from cryptography as
            # ValueError/TypeError/UnsupportedAlgorithm — all of them mean
            # "the configured key is unusable", never "bad request".
            logger.error("Apple: APPLE_PRIVATE_KEY could not sign the client_secret: %s", exc)
            raise AppleNotConfigured("APPLE_PRIVATE_KEY") from exc

        cls._cache_set(cls.CLIENT_SECRET_CACHE_KEY, cls.CLIENT_SECRET_TTL_SECONDS, client_secret)
        return client_secret

    @classmethod
    def exchange_authorization_code(cls, authorization_code: str, expected_subject: str) -> dict:
        """
        Exchanges the one-time authorization code for Apple tokens. No
        redirect_uri — the native flow never had one. Cross-checks the
        returned id_token's sub against the already-verified identity token
        so a code can't be swapped in.
        """
        client_secret = cls._generate_client_secret()

        try:
            response = requests.post(
                APPLE_TOKEN_URL,
                data={
                    "client_id": settings.APPLE_CLIENT_ID,
                    "client_secret": client_secret,
                    "code": authorization_code,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.error("Apple code exchange request failed: %s", exc)
            raise InvalidAppleCode() from exc

        if not response.ok:
            logger.warning("Apple code exchange failed: %s %s", response.status_code, response.text)
            raise InvalidAppleCode()

        try:
            token_response = response.json()
        except ValueError as exc:
            logger.error("Apple code exchange returned a non-JSON body.")
            raise InvalidAppleCode() from exc

        id_token = token_response.get("id_token")
        if not id_token:
            logger.warning("Apple code exchange response carried no id_token.")
            raise InvalidAppleCode()

        try:
            claims = jwt.decode(id_token, options={"verify_signature": False})
        except jwt.PyJWTError as exc:
            raise InvalidAppleCode() from exc

        if claims.get("sub") != expected_subject:
            raise InvalidAppleCode()

        return token_response
