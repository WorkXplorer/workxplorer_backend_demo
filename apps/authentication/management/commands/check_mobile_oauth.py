"""
Verifies everything about mobile OAuth that does NOT need a phone in your hand.

Run it on the box that serves /auth/mobile/* (staging or production):

    python manage.py check_mobile_oauth

Each check prints OK / FAIL with the reason. The Apple checks are the useful
ones: signing a client_secret proves the .p8 is loadable, and the live probe
asks Apple itself whether the credentials are accepted — Apple answers
invalid_grant (credentials fine, only our throwaway code is bad) or
invalid_client (credentials wrong), which is exactly the question an iOS
device would otherwise have to answer for us.
"""

import json
import time

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.authentication.services.apple_client import (
    APPLE_JWKS_URL,
    APPLE_TOKEN_URL,
    PEM_PRIVATE_KEY_HEADER,
    AppleClient,
    AppleNotConfigured,
    AppleUnavailable,
)
from apps.authentication.services.google_verifier import (
    CERTS_CACHE_KEY,
    GOOGLE_CERTS_URL,
    GoogleUnavailable,
    InvalidGoogleToken,
    verify_google_id_token,
)
from apps.authentication.services.oauth_challenge_service import OAuthChallengeService
from apps.authentication.services.provider_cache import cache_get


class Command(BaseCommand):
    help = "Check the mobile Google/Apple sign-in configuration without needing a device."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Skip the checks that call Apple/Google (config-only run).",
        )

    def handle(self, *args, **options):
        self.failures = 0
        self.offline = options["offline"]

        self.stdout.write(self.style.MIGRATE_HEADING("Shared"))
        self._check_mobile_key()
        self._check_challenge_ttl()
        self._check_redis()

        self.stdout.write(self.style.MIGRATE_HEADING("Google"))
        self._check_google_audience()
        if not self.offline:
            self._check_google_certs()
        self._check_google_certs_cache()

        self.stdout.write(self.style.MIGRATE_HEADING("Apple"))
        self._check_apple_settings()
        self._check_apple_client_secret()
        self._check_provider_token_key()
        if not self.offline:
            self._check_apple_jwks()
            self._check_apple_credentials()

        self.stdout.write("")
        if self.failures:
            self.stderr.write(self.style.ERROR(f"{self.failures} check(s) failed."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("All checks passed."))

    # --- reporting -----------------------------------------------------------

    def _ok(self, label, detail=""):
        self.stdout.write(f"  {self.style.SUCCESS('OK')}   {label}" + (f" — {detail}" if detail else ""))

    def _fail(self, label, detail):
        self.failures += 1
        self.stdout.write(f"  {self.style.ERROR('FAIL')} {label} — {detail}")

    def _warn(self, label, detail):
        self.stdout.write(f"  {self.style.WARNING('WARN')} {label} — {detail}")

    # --- shared --------------------------------------------------------------

    def _check_mobile_key(self):
        if getattr(settings, "MOBILE_APP_API_KEY", None):
            self._ok("MOBILE_APP_API_KEY set")
        else:
            self._fail("MOBILE_APP_API_KEY", "unset — every /auth/mobile/* call returns 403")

    def _check_challenge_ttl(self):
        ttl = OAuthChallengeService.ttl_seconds()
        detail = f"{ttl}s ({ttl // 60} min)"
        if ttl < 300:
            self._warn("OAUTH_CHALLENGE_TTL_SECONDS", f"{detail} — short for a native sign-in detour")
        else:
            self._ok("OAUTH_CHALLENGE_TTL_SECONDS", detail)

    def _check_redis(self):
        try:
            AppleClient._get_redis_connection().ping()
            self._ok("Redis reachable", "JWKS + client_secret caching active")
        except Exception as exc:
            self._warn("Redis unreachable", f"{exc} — logins still work, every one refetches Apple's JWKS")

    # --- google --------------------------------------------------------------

    def _check_google_audience(self):
        audience = getattr(settings, "GOOGLE_SERVER_CLIENT_ID", None)
        if not audience:
            self._fail("GOOGLE_SERVER_CLIENT_ID", "unset — no audience to verify ID tokens against")
            return
        self._ok("GOOGLE_SERVER_CLIENT_ID", audience)
        if not audience.endswith(".apps.googleusercontent.com"):
            self._warn("GOOGLE_SERVER_CLIENT_ID", "does not look like a Google OAuth client id")
        self.stdout.write(
            "       note: the iOS app must send the ID token minted for THIS client id\n"
            "       (its webClientId/serverClientId), not the iOS client id."
        )

    def _check_google_certs(self):
        started = time.monotonic()
        try:
            response = requests.get(GOOGLE_CERTS_URL, timeout=10)
            response.raise_for_status()
            elapsed = time.monotonic() - started
        except Exception as exc:
            self._fail("Google certs endpoint", f"{exc} — ID token verification will fail with 503")
            return

        detail = f"{len(response.json())} key(s) in {elapsed:.2f}s"
        if elapsed > 1.0:
            self._warn(
                "Google certs endpoint slow",
                f"{detail} — every uncached verification pays this, and the app may time out first",
            )
        else:
            self._ok("Google certs endpoint reachable", detail)

    def _check_google_certs_cache(self):
        """
        The certs are fetched on the critical path of every Google login, so a
        cold cache is the difference between a local verification and an
        outbound round-trip the mobile client may not wait for.
        """
        if cache_get(CERTS_CACHE_KEY):
            self._ok("Google certs cached", "logins verify without an outbound fetch")
            return
        if self.offline:
            self._warn("Google certs not cached", "first login after a restart pays the fetch")
            return

        started = time.monotonic()
        try:
            verify_google_id_token("not.a.real.token")
        except InvalidGoogleToken:
            pass
        except GoogleUnavailable as exc:
            self._fail("Google certs fetch", f"{exc.__cause__ or exc}")
            return
        elapsed = time.monotonic() - started

        if cache_get(CERTS_CACHE_KEY):
            self._ok("Google certs cached", f"warmed in {elapsed:.2f}s; later logins skip the fetch")
        else:
            self._warn("Google certs not cached", "check Redis — every login will refetch them")

    # --- apple ---------------------------------------------------------------

    def _check_apple_settings(self):
        for name in ("APPLE_TEAM_ID", "APPLE_CLIENT_ID", "APPLE_KEY_ID"):
            value = getattr(settings, name, None)
            if value:
                self._ok(name, value)
            else:
                self._fail(name, "unset")

        stored = (getattr(settings, "APPLE_PRIVATE_KEY", "") or "").strip()
        key = AppleClient._normalized_private_key()
        if not key:
            self._fail("APPLE_PRIVATE_KEY", "unset")
        elif stored.startswith("$(") or stored.startswith("`") or "$(cat" in stored:
            self._fail(
                "APPLE_PRIVATE_KEY",
                f"holds an unexpanded shell command ({stored[:40]}...) — a .env file is not a shell, "
                "so it was stored literally. Put the key's actual contents there: run "
                "`awk 'BEGIN{ORS=\"\\\\n\"} {print}' AuthKey_XXXX.p8` and paste that output, in quotes",
            )
        elif PEM_PRIVATE_KEY_HEADER not in key:
            self._fail(
                "APPLE_PRIVATE_KEY",
                "set, but not a PEM and not recoverable — the value must be the contents of "
                "AuthKey_XXXX.p8, BEGIN/END lines included (single line with literal \\n is fine)",
            )
        elif PEM_PRIVATE_KEY_HEADER not in stored.replace("\\n", "\n"):
            self._warn(
                "APPLE_PRIVATE_KEY",
                "stored without the PEM armor — recovered, but store the full .p8 contents instead",
            )
        else:
            self._ok("APPLE_PRIVATE_KEY", f"PEM, {len(key.splitlines())} lines")

    def _check_apple_client_secret(self):
        try:
            secret = AppleClient._generate_client_secret(force_refresh=True)
            self._ok("Apple client_secret signs", f"{len(secret)} chars, ES256")
        except AppleNotConfigured as exc:
            self._fail("Apple client_secret", f"cannot be signed ({exc}) — this is what returns 503 to the app")

    def _check_provider_token_key(self):
        key = getattr(settings, "AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY", None)
        if not key:
            self._fail("AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY", "unset — Apple login fails after the code exchange")
            return
        try:
            fernet = Fernet(key)
            assert fernet.decrypt(fernet.encrypt(b"probe")) == b"probe"
            self._ok("AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY", "valid Fernet key, round-trips")
        except Exception as exc:
            self._fail("AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY", f"not a usable Fernet key ({exc})")

    def _check_apple_jwks(self):
        try:
            jwks = AppleClient._get_jwks(force_refresh=True)
            self._ok("Apple JWKS reachable", f"{len(jwks.get('keys', []))} key(s) from {APPLE_JWKS_URL}")
        except AppleUnavailable as exc:
            self._fail("Apple JWKS", f"unreachable ({exc.__cause__ or exc})")

    def _check_apple_credentials(self):
        """
        The real device-free test: exchange a code we know is bad. Apple checks
        client_id/client_secret BEFORE the code, so its error tells us which
        half is wrong.
        """
        try:
            client_secret = AppleClient._generate_client_secret()
        except AppleNotConfigured:
            self._fail("Apple credentials", "skipped — client_secret could not be signed")
            return

        try:
            response = requests.post(
                APPLE_TOKEN_URL,
                data={
                    "client_id": settings.APPLE_CLIENT_ID,
                    "client_secret": client_secret,
                    "code": "check-mobile-oauth-probe",
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            self._fail("Apple credentials", f"token endpoint unreachable ({exc})")
            return

        error = body.get("error")
        if error == "invalid_grant":
            self._ok(
                "Apple credentials accepted",
                "Apple rejected only the throwaway code — team id, key id, client id and .p8 all check out",
            )
        elif error == "invalid_client":
            self._fail(
                "Apple credentials rejected",
                "invalid_client — APPLE_TEAM_ID / APPLE_KEY_ID / APPLE_CLIENT_ID and the .p8 don't agree. "
                "APPLE_CLIENT_ID must be the app's bundle id for a native iOS sign-in (not a Services ID), "
                "and the key must belong to that team",
            )
        else:
            self._warn("Apple credentials", f"unexpected reply: {json.dumps(body)[:300]}")
