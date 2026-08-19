import os
import tempfile
import importlib
import hashlib
import logging
import time
from collections import OrderedDict
from functools import lru_cache
from typing import Optional
from typing import Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


class VirusScanError(Exception):
    """Base antivirus scan error."""
    error_code: str = "ANTIVIRUS_SCAN_FAILED"


class FileInfectedError(VirusScanError):
    """Virus or malware was detected in the uploaded file."""
    error_code = "FILE_INFECTED"

    def __init__(self, threat: str = "malware"):
        self.threat = threat
        super().__init__(threat)


class ScanUnavailableError(VirusScanError):
    """Antivirus service is unavailable or the scan could not complete."""
    error_code = "ANTIVIRUS_SCAN_FAILED"


class FileTooLargeError(VirusScanError):
    """File exceeds the allowed size limit."""
    error_code = "FILE_TOO_LARGE"


class InvalidFileTypeError(VirusScanError):
    """File extension is not in the allowed list."""
    error_code = "INVALID_FILE_TYPE"


def _normalize_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def is_scan_enabled() -> bool:
    return _normalize_bool(getattr(settings, "CLAMAV_SCAN_ENABLED", True), True)


def is_fail_open() -> bool:
    return _normalize_bool(getattr(settings, "CLAMAV_FAIL_OPEN", False), False)


def get_engine() -> str:
    return str(getattr(settings, "CLAMAV_ENGINE", "clamav-client")).strip().lower()


def is_cache_enabled() -> bool:
    return _normalize_bool(getattr(settings, "CLAMAV_CACHE_ENABLED", True), True)


def get_cache_ttl_seconds() -> int:
    try:
        return int(getattr(settings, "CLAMAV_CACHE_TTL_SECONDS", 3600))
    except Exception:
        return 3600


def _normalize_scan_result(state, details, passed):
    if isinstance(state, str):
        state = state.strip().upper() or None

    if passed is None:
        if state == "OK":
            passed = True
        elif state == "FOUND":
            passed = False

    return state, details, passed


def _is_definitive_scan_result(state, passed) -> bool:
    return state == "FOUND" or passed is True


def _should_cache_scan_result(state, passed) -> bool:
    return _is_definitive_scan_result(state, passed)


def _build_scanner_config() -> dict:
    backend = getattr(settings, "CLAMAV_BACKEND", "clamd")
    if backend == "clamd":
        return {
            "backend": "clamd",
            "address": getattr(settings, "CLAMAV_ADDRESS", "/var/run/clamav/clamd.ctl"),
            "timeout": float(getattr(settings, "CLAMAV_TIMEOUT", 15.0)),
            "stream": _normalize_bool(getattr(settings, "CLAMAV_STREAM", True), True),
        }
    if backend == "clamscan":
        return {
            "backend": "clamscan",
            "max_file_size": float(getattr(settings, "CLAMAV_MAX_FILE_SIZE_MB", 2000)),
            "max_scan_size": float(getattr(settings, "CLAMAV_MAX_SCAN_SIZE_MB", 2000)),
        }
    raise VirusScanError(f"Unsupported CLAMAV_BACKEND: {backend}")


def _get_address() -> str:
    return str(getattr(settings, "CLAMAV_ADDRESS", "/var/run/clamav/clamd.ctl")).strip()


def _split_host_port(address: str) -> Optional[Tuple[str, int]]:
    if ":" not in address:
        return None
    host, port = address.rsplit(":", 1)
    try:
        return host.strip(), int(port.strip())
    except ValueError:
        return None


def _permission_denied_hint() -> str:
    address = _get_address()
    return (
        f"Permission denied for clamd socket/address '{address}'. "
        "Either grant socket permissions for the app user, "
        "or configure TCP by setting CLAMAV_ADDRESS=127.0.0.1:3310."
    )


class _BoundedTTLCache:
    """LRU cache with per-entry TTL and a hard maximum size to prevent unbounded growth."""

    def __init__(self, maxsize: int = 1024):
        self._maxsize = maxsize
        self._store: OrderedDict = OrderedDict()

    def get(self, key: str):
        if key not in self._store:
            return None
        expires_at, value = self._store[key]
        if expires_at < time.time():
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value, ttl: int) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time() + ttl, value)
        # Evict oldest entries when over capacity
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)


_scan_result_cache = _BoundedTTLCache(maxsize=1024)


def _get_cached_scan(file_hash: str):
    if not is_cache_enabled():
        return None
    cached = _scan_result_cache.get(file_hash)
    if cached is None:
        return None

    state, details, passed = cached
    # In fail-open mode, never block uploads based only on stale cached malware results.
    if is_fail_open() and state == "FOUND":
        return None

    return state, details, passed


def _set_cached_scan(file_hash: str, state, details, passed) -> None:
    if not is_cache_enabled() or not file_hash:
        return
    if is_fail_open() and state == "FOUND":
        return
    ttl = max(get_cache_ttl_seconds(), 1)
    _scan_result_cache.set(file_hash, (state, details, passed), ttl)


@lru_cache(maxsize=1)
def _get_scanner():
    try:
        clamav_module = importlib.import_module("clamav_client")
        get_scanner = getattr(clamav_module, "get_scanner")
    except Exception as exc:
        raise VirusScanError("clamav-client package is not installed") from exc

    config = _build_scanner_config()
    try:
        return get_scanner(config)
    except Exception as exc:
        raise VirusScanError(f"Unable to initialize ClamAV scanner: {exc}") from exc


@lru_cache(maxsize=1)
def _get_clamd_client():
    try:
        clamd_module = importlib.import_module("clamd")
    except Exception as exc:
        raise VirusScanError("clamd package is not installed") from exc

    address = _get_address()
    host_port = _split_host_port(address)
    timeout = float(getattr(settings, "CLAMAV_TIMEOUT", 15.0))
    try:
        if host_port:
            host, port = host_port
            return clamd_module.ClamdNetworkSocket(host=host, port=port, timeout=timeout)
        return clamd_module.ClamdUnixSocket(path=address)
    except Exception as exc:
        raise VirusScanError(f"Unable to initialize clamd client: {exc}") from exc


def _scan_path(file_path: str):
    scanner = _get_scanner()
    try:
        return scanner.scan(file_path)
    except Exception as exc:
        raise VirusScanError(f"ClamAV scan failed: {exc}") from exc


def _scan_path_with_clamd(file_path: str):
    client = _get_clamd_client()
    try:
        report = client.scan(file_path)
    except Exception as exc:
        raise VirusScanError(f"ClamAV scan failed: {exc}") from exc

    if not report:
        return "ERROR", "Empty scan result", False

    first_key = next(iter(report.keys()))
    state, details = report[first_key]
    state = (state or "").upper()

    if state == "OK":
        return state, None, True
    if state == "FOUND":
        return state, details or "malware", False
    return state or "ERROR", details or "unknown scanner error", False


def _scan_with_engine(file_path: str, engine: str):
    if engine == "clamav-client":
        result = _scan_path(file_path)
        return _normalize_scan_result(
            getattr(result, "state", None),
            getattr(result, "details", None),
            getattr(result, "passed", None),
        )
    if engine == "clamd":
        return _normalize_scan_result(*_scan_path_with_clamd(file_path))
    raise VirusScanError(f"Unsupported CLAMAV_ENGINE: {engine}")



def _scan_for_embedded_payloads(file_path: str, original_file_name: str) -> None:
    """Manually inspect specific file types for deeply embedded payloads 
       that standard AV heuristic engines might allow through (like polyglots)."""
    file_name = (original_file_name or "").lower()
    
    try:
        with open(file_path, "rb") as f:
            # Most uploads are restricted by MAX_FILE_SIZE, safe to read 10MB
            content = f.read(10 * 1024 * 1024) 
            lower_content = content.lower()

            # 1. Standard EICAR fallback (because engines may ignore it in non-executable wrappers like .svg)
            if b"x5o!p%@ap[4\\pzx54(p^)7cc)7}$eicar-standard-antivirus-test-file!$h+h*" in lower_content:
                raise FileInfectedError("Eicar-Test-Signature")
            
            # 2. SVG files: Block XSS payloads (scripts, iframes, javascript endpoints)
            if file_name.endswith('.svg') or b'<svg' in lower_content[:2048]:
                if (b'<script' in lower_content or 
                    b'javascript:' in lower_content or 
                    b'<iframe' in lower_content or 
                    b'onload=' in lower_content or 
                    b'onerror=' in lower_content):
                    raise FileInfectedError("Malicious script detected in SVG (XSS Payload)")
            
            # 3. Image & Generic files : Block Polyglot files (e.g. <?php embedded tags)
            if file_name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.zip', '.pdf', '.doc', '.docx')):
                if (b'<?php' in lower_content or 
                    b'<jsp' in lower_content or 
                    b'<%=' in lower_content):
                    raise FileInfectedError("Embedded executable web-shell (Polyglot) detected")
                    
                # Images should not natively contain script tags (Polyglot XSS attacks)
                if file_name.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    if b'<script' in lower_content or b'javascript:' in lower_content:
                        raise FileInfectedError("Embedded script (XSS Polyglot) detected in Image")
                        
    except VirusScanError:
        raise
    except Exception:
        logger.exception("Error during embedded payload scan")


def scan_uploaded_file(uploaded_file) -> None:
    if not uploaded_file or isinstance(uploaded_file, str):
        return
    if not is_scan_enabled():
        return

    temp_path = None
    try:
        if hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(0)
            except Exception:
                logger.warning("Unable to seek uploaded file, scan may fail if file is not at the beginning")

        file_hash_builder = hashlib.sha256()
        tmp = tempfile.NamedTemporaryFile(delete=False)
        temp_path = tmp.name
        with tmp:
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
                file_hash_builder.update(chunk)
        file_hash = file_hash_builder.hexdigest()
        cached_scan = _get_cached_scan(file_hash)

        if cached_scan is not None:
            state, details, passed = cached_scan
        else:
            preferred_engine = get_engine()
            engine_order = [preferred_engine] + [
                engine for engine in ("clamav-client", "clamd") if engine != preferred_engine
            ]

            last_error = None
            state = details = passed = None
            fallback_result = None
            for engine in engine_order:
                try:
                    current_state, current_details, current_passed = _scan_with_engine(temp_path, engine)
                    last_error = None
                    if _is_definitive_scan_result(current_state, current_passed):
                        state, details, passed = current_state, current_details, current_passed
                        break
                    fallback_result = (current_state, current_details, current_passed)
                    continue
                except Exception as exc:
                    last_error = exc
                    continue

            if state is None and fallback_result is not None:
                state, details, passed = fallback_result

            if last_error is not None and fallback_result is None:
                if is_fail_open():
                    return
                raise ScanUnavailableError(
                    f"Antivirus scan failed for all engines: {last_error}"
                )

            if _should_cache_scan_result(state, passed):
                _set_cached_scan(file_hash, state, details, passed)

        if state == "FOUND":
            raise FileInfectedError(details or "malware")
        
        if passed is False or passed is None:
            if is_fail_open():
                return
            raise ScanUnavailableError(details or "scanner unavailable")
            
        # Perform explicit polyglot / EICAR deep scan as a final step
        # ONLY if the ClamAV container is up and passed the file
        _scan_for_embedded_payloads(temp_path, getattr(uploaded_file, 'name', ''))
        
    except FileInfectedError:
        raise
    except VirusScanError:
        raise
    except Exception as exc:
        error_text = str(exc)
        if "permission denied" in error_text.lower() and not is_fail_open():
            raise ScanUnavailableError(_permission_denied_hint()) from exc
        if is_fail_open():
            return
        raise ScanUnavailableError(f"Antivirus scan error: {exc}") from exc
    finally:
        if hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(0)
            except Exception:
                # Do not mask scan errors with seek-related issues.
                logger.warning("Unable to seek uploaded file, scan may fail if file is not at the beginning")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.warning(f"Unable to delete temporary file at {temp_path}")
