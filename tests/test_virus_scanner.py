"""
Unit tests for utils/virus_scanner.py

Covers the settings matrix:
  - CLAMAV_SCAN_ENABLED  (enabled / disabled)
  - Virus found           → FileInfectedError
  - Service unavailable   → ScanUnavailableError  (fail_open=False)
  - Service unavailable   → no exception          (fail_open=True)
  - Result caching        → duplicate files skip the scan engine
  - _BoundedTTLCache      → LRU eviction and TTL expiry

All scanner / engine calls are mocked so no running ClamAV daemon is needed.
"""

import time
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from utils.fields.certificate import build_certificate_error_payload
from utils.virus_scanner import (
    _BoundedTTLCache,
    FileInfectedError,
    InvalidFileTypeError,
    ScanUnavailableError,
    VirusScanError,
    scan_uploaded_file,
    _scan_result_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(content: bytes = b"hello world", name: str = "test.txt") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="text/plain")


class _EngineResult:
    """Simple value object matching what _scan_with_engine returns."""

    def __init__(self, state, details, passed):
        self.state = state
        self.details = details
        self.passed = passed


# ---------------------------------------------------------------------------
# _BoundedTTLCache - unit tests (no Django DB / settings needed)
# ---------------------------------------------------------------------------

class BoundedTTLCacheTests(TestCase):
    """Tests for the in-memory LRU + TTL cache."""

    def setUp(self):
        self.cache = _BoundedTTLCache(maxsize=3)

    def test_basic_set_and_get(self):
        self.cache.set("a", "val_a", ttl=60)
        self.assertEqual(self.cache.get("a"), "val_a")

    def test_missing_key_returns_none(self):
        self.assertIsNone(self.cache.get("does_not_exist"))

    def test_expired_entry_returns_none(self):
        self.cache.set("b", "val_b", ttl=0)
        # ttl=0 means expires_at = now + 0; give it a tiny sleep to expire
        time.sleep(0.01)
        self.assertIsNone(self.cache.get("b"))

    def test_lru_eviction_removes_oldest(self):
        self.cache.set("x", 1, ttl=60)
        self.cache.set("y", 2, ttl=60)
        self.cache.set("z", 3, ttl=60)  # cache is now full (maxsize=3)
        # Access "x" so it becomes the most-recently-used
        self.cache.get("x")
        # Adding "w" should evict the LRU entry, which is now "y"
        self.cache.set("w", 4, ttl=60)
        self.assertIsNone(self.cache.get("y"), "LRU entry 'y' should have been evicted")
        self.assertIsNotNone(self.cache.get("x"))
        self.assertIsNotNone(self.cache.get("z"))
        self.assertIsNotNone(self.cache.get("w"))

    def test_overwrite_updates_value(self):
        self.cache.set("k", "first", ttl=60)
        self.cache.set("k", "second", ttl=60)
        self.assertEqual(self.cache.get("k"), "second")

    def test_max_size_never_exceeded(self):
        for i in range(20):
            self.cache.set(str(i), i, ttl=60)
        self.assertLessEqual(len(self.cache._store), 3)


# ---------------------------------------------------------------------------
# scan_uploaded_file - settings-matrix tests
# ---------------------------------------------------------------------------

@override_settings(
    CLAMAV_SCAN_ENABLED=False,
    CLAMAV_CACHE_ENABLED=False,
)
class ScanDisabledTests(TestCase):
    """When CLAMAV_SCAN_ENABLED is False scanning should be a no-op."""

    def test_clean_file_passes_silently(self):
        """scan_uploaded_file should return without raising when scan is disabled."""
        f = _make_file()
        # Should not raise anything
        result = scan_uploaded_file(f)
        self.assertIsNone(result)

    def test_none_file_passes(self):
        self.assertIsNone(scan_uploaded_file(None))

    def test_string_value_passes(self):
        """String paths (non-file objects) are always skipped."""
        self.assertIsNone(scan_uploaded_file("/some/path.txt"))


@override_settings(
    CLAMAV_SCAN_ENABLED=True,
    CLAMAV_FAIL_OPEN=False,
    CLAMAV_CACHE_ENABLED=False,
)
class ScanEnabledTests(TestCase):
    """Core scan scenarios when ClamAV scanning is enabled."""

    def _patch_engine(self, state, details, passed):
        """Patch _scan_with_engine to return a fixed tuple."""
        return patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=(state, details, passed),
        )

    def test_clean_file_does_not_raise(self):
        with self._patch_engine("OK", None, True):
            scan_uploaded_file(_make_file())  # no exception

    def test_infected_file_raises_file_infected_error(self):
        with self._patch_engine("FOUND", "Eicar-Test-Signature", False):
            with self.assertRaises(FileInfectedError) as ctx:
                scan_uploaded_file(_make_file())
            self.assertEqual(ctx.exception.threat, "Eicar-Test-Signature")

    def test_infected_file_error_code(self):
        with self._patch_engine("FOUND", "malware", False):
            with self.assertRaises(FileInfectedError) as ctx:
                scan_uploaded_file(_make_file())
            self.assertEqual(ctx.exception.error_code, "FILE_INFECTED")

    def test_inconclusive_result_retries_next_engine_and_detects_virus(self):
        with patch(
            "utils.virus_scanner._scan_with_engine",
            side_effect=[
                ("ERROR", "temporary parser mismatch", False),
                ("FOUND", "Eicar-Test-Signature", False),
            ],
        ) as mock_engine:
            with self.assertRaises(FileInfectedError) as ctx:
                scan_uploaded_file(_make_file())
            self.assertEqual(ctx.exception.threat, "Eicar-Test-Signature")
        self.assertEqual(mock_engine.call_count, 2)

    def test_scanner_error_fail_closed_raises_unavailable(self):
        """When engine raises and fail_open=False → ScanUnavailableError."""
        with patch(
            "utils.virus_scanner._scan_with_engine",
            side_effect=VirusScanError("connection refused"),
        ):
            with self.assertRaises(ScanUnavailableError):
                scan_uploaded_file(_make_file())

    def test_passed_false_without_found_raises_unavailable(self):
        """passed=False without FOUND state is an ambiguous scan failure."""
        with self._patch_engine("ERROR", "unknown error", False):
            with self.assertRaises(ScanUnavailableError):
                scan_uploaded_file(_make_file())

    def test_none_passed_fail_closed_raises_unavailable(self):
        """passed=None with fail_open=False → ScanUnavailableError."""
        with self._patch_engine("UNKNOWN", None, None):
            with self.assertRaises(ScanUnavailableError):
                scan_uploaded_file(_make_file())


@override_settings(
    CLAMAV_SCAN_ENABLED=True,
    CLAMAV_FAIL_OPEN=True,
    CLAMAV_CACHE_ENABLED=False,
)
class ScanFailOpenTests(TestCase):
    """When fail_open=True an unavailable scanner should not block uploads."""

    def test_scanner_error_fail_open_does_not_raise(self):
        with patch(
            "utils.virus_scanner._scan_with_engine",
            side_effect=Exception("connection refused"),
        ):
            # Should NOT raise - fail-open means we let the file through
            scan_uploaded_file(_make_file())

    def test_none_passed_fail_open_does_not_raise(self):
        with patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=("UNKNOWN", None, None),
        ):
            scan_uploaded_file(_make_file())

    def test_virus_found_always_raises_regardless_of_fail_open(self):
        """Fail-open must NOT suppress a positive virus detection."""
        with patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=("FOUND", "malware", False),
        ):
            with self.assertRaises(FileInfectedError):
                scan_uploaded_file(_make_file())


@override_settings(
    CLAMAV_SCAN_ENABLED=True,
    CLAMAV_FAIL_OPEN=False,
    CLAMAV_CACHE_ENABLED=True,
    CLAMAV_CACHE_TTL_SECONDS=60,
)
class ScanCacheTests(TestCase):
    """Identical file content must only be scanned once."""

    def setUp(self):
        # Clear shared cache state between tests
        _scan_result_cache._store.clear()

    def test_second_upload_of_same_content_skips_engine(self):
        content = b"unique content for cache test"
        with patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=("OK", None, True),
        ) as mock_engine:
            scan_uploaded_file(_make_file(content))
            scan_uploaded_file(_make_file(content))  # same bytes
        # Engine should only have been called once
        self.assertEqual(mock_engine.call_count, 1)

    def test_different_content_scanned_separately(self):
        with patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=("OK", None, True),
        ) as mock_engine:
            scan_uploaded_file(_make_file(b"content_alpha"))
            scan_uploaded_file(_make_file(b"content_beta"))
        self.assertEqual(mock_engine.call_count, 2)

    def test_cached_infected_result_still_raises(self):
        """A previously cached FOUND result should re-raise FileInfectedError."""
        content = b"infected content"
        with patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=("FOUND", "TestVirus", False),
        ):
            with self.assertRaises(FileInfectedError):
                scan_uploaded_file(_make_file(content))

        # Second call: engine not invoked but cached FOUND should still raise
        with patch(
            "utils.virus_scanner._scan_with_engine",
        ) as mock_engine:
            with self.assertRaises(FileInfectedError):
                scan_uploaded_file(_make_file(content))
            mock_engine.assert_not_called()

    def test_unavailable_result_is_not_cached(self):
        content = b"scan failure should not be cached"
        with patch(
            "utils.virus_scanner._scan_with_engine",
            return_value=("ERROR", "temporary scanner failure", False),
        ) as mock_engine:
            with self.assertRaises(ScanUnavailableError):
                scan_uploaded_file(_make_file(content))
            with self.assertRaises(ScanUnavailableError):
                scan_uploaded_file(_make_file(content))

        self.assertEqual(mock_engine.call_count, 4)


# ---------------------------------------------------------------------------
# Exception hierarchy sanity checks
# ---------------------------------------------------------------------------

class ExceptionHierarchyTests(TestCase):
    """Ensure all custom exceptions are proper VirusScanError subclasses."""

    def test_file_infected_is_virus_scan_error(self):
        self.assertIsInstance(FileInfectedError("test"), VirusScanError)

    def test_scan_unavailable_is_virus_scan_error(self):
        self.assertIsInstance(ScanUnavailableError("test"), VirusScanError)

    def test_file_infected_stores_threat(self):
        exc = FileInfectedError("TestVirus.HEUR")
        self.assertEqual(exc.threat, "TestVirus.HEUR")

    def test_file_infected_default_threat(self):
        exc = FileInfectedError()
        self.assertEqual(exc.threat, "malware")

    def test_invalid_file_type_is_virus_scan_error(self):
        self.assertIsInstance(InvalidFileTypeError("bad ext"), VirusScanError)


class CertificateErrorPayloadTests(TestCase):
    def test_infected_file_payload_uses_file_infected_response(self):
        payload = build_certificate_error_payload(
            [FileInfectedError("Eicar-Test-Signature")],
            "en",
        )

        self.assertEqual(payload["code"], "FILE_INFECTED")
        self.assertIn("certificates", payload["field_errors"])

    def test_scan_unavailable_payload_uses_scan_failed_response(self):
        payload = build_certificate_error_payload(
            [ScanUnavailableError("connection refused")],
            "en",
        )

        self.assertEqual(payload["code"], "ANTIVIRUS_SCAN_FAILED")
        self.assertIn("certificates", payload["field_errors"])
        self.assertIn(
            "The file did not pass the antivirus check.",
            payload["field_errors"]["certificates"],
        )
