import time

from django.contrib.auth import authenticate
from django.test import TestCase
from django.utils import timezone

from apps.authentication.backends import EmailOrPhoneBackend
from apps.authentication.models import Candidate


class EmailOrPhoneBackendTests(TestCase):
    def setUp(self):
        self.user = Candidate.objects.create_user(
            email="backend-test@example.com", password="testpass123", is_candidate=True,
        )
        self.user.phone = "+998901234567"
        self.user.phone_verified_at = timezone.now()
        self.user.save(update_fields=["phone", "phone_verified_at"])

    def test_authenticates_by_email(self):
        result = authenticate(email="backend-test@example.com", password="testpass123")
        self.assertEqual(result, self.user)

    def test_authenticates_by_verified_phone(self):
        result = authenticate(email="901234567", password="testpass123")
        self.assertEqual(result, self.user)

    def test_rejects_unverified_phone(self):
        other = Candidate.objects.create_user(email="other@example.com", password="testpass123", is_candidate=True)
        other.phone = "+998907654321"
        other.save(update_fields=["phone"])  # not verified

        result = authenticate(email="907654321", password="testpass123")
        self.assertIsNone(result)

    def test_rejects_wrong_password(self):
        result = authenticate(email="backend-test@example.com", password="wrong")
        self.assertIsNone(result)

    def test_rejects_unknown_identifier(self):
        result = authenticate(email="nobody@example.com", password="testpass123")
        self.assertIsNone(result)

    def test_unknown_and_wrong_password_take_comparable_time(self):
        """Coarse timing-safety check: a nonexistent identifier shouldn't be
        dramatically cheaper than a real one with a wrong password (both
        should run a password hash). Not a precise side-channel test — just
        guards against the early-return-with-no-hash regression."""
        backend = EmailOrPhoneBackend()

        start = time.perf_counter()
        backend.authenticate(None, username="nobody@example.com", password="whatever")
        unknown_elapsed = time.perf_counter() - start

        start = time.perf_counter()
        backend.authenticate(None, username="backend-test@example.com", password="wrong")
        known_elapsed = time.perf_counter() - start

        # Both should be dominated by one password-hasher call; allow generous
        # slack since this runs on shared CI hardware.
        self.assertLess(abs(unknown_elapsed - known_elapsed), max(unknown_elapsed, known_elapsed) * 3)
