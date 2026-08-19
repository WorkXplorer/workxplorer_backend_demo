import json
import logging
import re

import jwt
from django.conf import settings
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from apps.authentication.services.provider_cache import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

# The URL google-auth verifies Google ID tokens against. Pinned here so the
# caching wrapper below can recognise it; it is never taken from the token.
GOOGLE_CERTS_URL = id_token._GOOGLE_OAUTH2_CERTS_URL

CERTS_CACHE_KEY = "google:oauth2_certs"
CERTS_CACHE_DEFAULT_TTL_SECONDS = 60 * 60
CERTS_CACHE_MIN_TTL_SECONDS = 5 * 60
CERTS_CACHE_MAX_TTL_SECONDS = 24 * 60 * 60
CERTS_FETCH_TIMEOUT_SECONDS = 5


class InvalidGoogleToken(Exception):
    pass


class GoogleUnavailable(Exception):
    """Google's certs endpoint couldn't be reached — transient, not the caller's fault."""


class _CachedResponse:
    """Minimal google.auth.transport.Response for a cache hit."""

    status = 200
    headers: dict = {}

    def __init__(self, data: bytes):
        self.data = data


class _CachedCertsRequest(google_requests.Request):
    """
    google-auth re-fetches Google's signing certs on *every* verification —
    an uncached outbound round-trip on the critical path of each login, at
    the library's 120s default timeout. Serving that one URL from Redis
    keeps the login local, and every other request falls through untouched,
    so all of the actual token validation still happens inside google-auth.
    """

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        if method != "GET" or url != GOOGLE_CERTS_URL:
            return super().__call__(url, method, body, headers, timeout, **kwargs)

        cached = cache_get(CERTS_CACHE_KEY)
        if cached:
            return _CachedResponse(cached)

        # A hung certs fetch must not hold the request open for two minutes.
        response = super().__call__(
            url, method, body, headers, timeout or CERTS_FETCH_TIMEOUT_SECONDS, **kwargs
        )
        if response.status == 200:
            cache_set(CERTS_CACHE_KEY, _cache_ttl_from(response), response.data)
        return response


_google_request = _CachedCertsRequest()


def _cache_ttl_from(response) -> int:
    """Honour Google's own Cache-Control lifetime, clamped to something sane."""
    headers = getattr(response, "headers", None) or {}
    cache_control = headers.get("cache-control") or headers.get("Cache-Control") or ""
    match = re.search(r"max-age=(\d+)", cache_control)
    if not match:
        return CERTS_CACHE_DEFAULT_TTL_SECONDS
    return max(CERTS_CACHE_MIN_TTL_SECONDS, min(int(match.group(1)), CERTS_CACHE_MAX_TTL_SECONDS))


def _refresh_certs_if_key_is_unknown(id_token_str: str) -> None:
    """
    Cached certs go stale when Google rotates keys, which would lock every
    login out until the entry expired. A token signed by a key we haven't
    got is the signal to refetch — the same one-controlled-refresh dance the
    Apple client does.
    """
    cached = cache_get(CERTS_CACHE_KEY)
    if not cached:
        return

    try:
        kid = jwt.get_unverified_header(id_token_str).get("kid")
    except jwt.PyJWTError:
        return
    if not kid:
        return

    known_kids = _kids_in(cached)
    if known_kids and kid not in known_kids:
        logger.info("Google: certs cache has no key %s, dropping it to refetch.", kid)
        cache_delete(CERTS_CACHE_KEY)


def _kids_in(cached: bytes) -> set:
    """Google's certs come as {kid: x509} today and could come as a JWK set."""
    try:
        certs = json.loads(cached)
    except ValueError:
        return set()

    if isinstance(certs, dict) and "keys" in certs:
        return {key.get("kid") for key in certs["keys"]}
    if isinstance(certs, dict):
        return set(certs)
    return set()


def verify_google_id_token(id_token_str: str) -> dict:
    """
    Verifies signature/iss/aud/exp via the official google-auth library
    (not tokeninfo — that's diagnostic-only, never production). Returns
    {"subject", "email", "email_verified", "nonce"} — the caller matches
    "nonce" against the OAuthChallenge it consumed for this request, since
    the challenge only ever stored a digest, not the raw value. Raises
    InvalidGoogleToken on any verification failure, GoogleUnavailable if
    the certs fetch itself failed.
    """
    _refresh_certs_if_key_is_unknown(id_token_str)

    try:
        id_info = id_token.verify_oauth2_token(
            id_token_str, _google_request, settings.GOOGLE_SERVER_CLIENT_ID
        )
    except ValueError as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        raise InvalidGoogleToken() from exc
    except google_exceptions.GoogleAuthError as exc:
        # TransportError and friends are NOT ValueError: fetching Google's
        # signing certs can fail (DNS, egress, timeout) long after the token
        # itself is fine. That's a 503, never a 500 and never a 401.
        logger.error("Google certs fetch failed while verifying an ID token: %s", exc)
        raise GoogleUnavailable() from exc

    if not id_info.get("email_verified"):
        raise InvalidGoogleToken()

    email = id_info.get("email")
    if not email:
        # No email claim means the 'email' scope wasn't granted — the account
        # can't be resolved or created, but it's a bad request, not a crash.
        logger.warning("Google ID token carried no email claim (sub=%s).", id_info.get("sub"))
        raise InvalidGoogleToken()

    return {
        "subject": id_info["sub"],
        "email": email,
        "email_verified": True,
        "nonce": id_info.get("nonce"),
    }
