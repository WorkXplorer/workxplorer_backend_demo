"""
Vault Service integration for LMS grade synchronization.

The Vault service is a FastAPI microservice that securely stores and syncs
university student grades from LMS platforms. After a candidate registers
on WorkXplorer, they can link their university LMS account. The Vault
service fetches their grades, calculates WX scores, and categorizes subjects.

Note: The Vault service only allows connections from the production server
(LMS integration is remote). Local development cannot test actual LMS data exchange.
"""

import logging
import warnings

import requests
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


VAULT_TIMEOUT = 30  # seconds


class VaultServiceError(Exception):
    """Base exception for Vault service errors."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class VaultInvalidCredentialsError(VaultServiceError):
    """Raised when LMS credentials are invalid (401)."""

    def __init__(self, message: str = "Invalid LMS credentials"):
        super().__init__(message, status_code=401)


class VaultAlreadyRegisteredError(VaultServiceError):
    """Raised when student is already registered in Vault (409)."""

    def __init__(self, message: str = "Student already registered in Vault"):
        super().__init__(message, status_code=409)


class VaultBadRequestError(VaultServiceError):
    """Raised when request is invalid (400), e.g., invalid university ID."""

    def __init__(self, message: str = "Invalid request to Vault service"):
        super().__init__(message, status_code=400)


def register_student_in_vault(
    student_id: str,
    main_plat_id: str,
    lms_login: str,
    lms_password: str,
) -> dict:
    """
    Register a student with the Vault service to sync LMS grades.

    Sends the candidate's ID, university (edupartner) ID, and LMS credentials
    to the Vault service's /register endpoint.

    Args:
        student_id: The candidate's UUID (as string).
        main_plat_id: The edupartner's UUID (as string).
        lms_login: The candidate's LMS username.
        lms_password: The candidate's LMS password.

    Returns:
        dict with keys: student_id, message, sync_status ("success" or "pending")

    Raises:
        VaultInvalidCredentialsError: If LMS credentials are invalid (401).
        VaultAlreadyRegisteredError: If student is already registered (409).
        VaultBadRequestError: If main_plat_id is invalid (400).
        VaultServiceError: For other Vault service errors or connection issues.
    """
    vault_url = getattr(settings, "VAULT_SERVICE_URL", "http://localhost:8004")
    vault_token = getattr(settings, "VAULT_TOKEN", "")

    if not vault_url:
        raise VaultServiceError("VAULT_SERVICE_URL is not configured")

    if not vault_token:
        raise VaultServiceError("VAULT_TOKEN is not configured")

    if vault_url.startswith("http://"):
        logger.warning("Vault service URL uses HTTP (%s). Credentials will be sent in cleartext! Use HTTPS in production.", vault_url)
        warnings.warn("Vault service is using HTTP — LMS credentials will be sent in cleartext. Set VAULT_SERVICE_URL to an HTTPS URL in production.")

    url = f"{vault_url.rstrip('/')}/register"
    headers = {
        "X-Vault-Token": vault_token,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            url,
            json={
                "student_id": student_id,
                "main_plat_id": main_plat_id,
                "lms_login": lms_login,
                "lms_password": lms_password,
            },
            headers=headers,
            timeout=VAULT_TIMEOUT,
        )

    except requests.ConnectionError:
        logger.error(f"Failed to connect to Vault service at {vault_url}")
        raise VaultServiceError(
            "Unable to connect to the Vault service. Please try again later.",
            status_code=503,
        )
    except requests.Timeout:
        logger.error(f"Vault service request timed out ({VAULT_TIMEOUT}s)")
        raise VaultServiceError(
            "Vault service request timed out. Please try again later.",
            status_code=504,
        )
    except requests.RequestException as e:
        logger.error(f"Vault service request failed: {e}")
        raise VaultServiceError(
            "An error occurred while communicating with the Vault service.",
            status_code=502,
        )

    # Handle response status codes
    if response.status_code == 200:
        data = response.json()
        logger.info(
            f"Student {student_id} registered in Vault — sync_status: {data.get('sync_status')}"
        )
        return data

    if response.status_code == 401:
        detail = _extract_detail(response)
        logger.warning(f"Invalid LMS credentials for student {student_id}: {detail}")
        raise VaultInvalidCredentialsError(detail or "Invalid LMS credentials")

    if response.status_code == 409:
        detail = _extract_detail(response)
        logger.warning(f"Student {student_id} already registered in Vault")
        raise VaultAlreadyRegisteredError(detail or "Student already registered in Vault")

    if response.status_code == 400:
        detail = _extract_detail(response)
        logger.warning(f"Bad request to Vault for student {student_id}: {detail}")
        raise VaultBadRequestError(
            _("The selected university is not supported for LMS verification.")
        )

    # Unexpected status code
    detail = _extract_detail(response)
    logger.error(
        f"Unexpected Vault response {response.status_code} for student {student_id}: {detail}"
    )
    raise VaultServiceError(
        f"Vault service returned an unexpected error: {detail or response.status_code}",
        status_code=response.status_code,
    )


def get_universities_from_vault() -> list:
    """
    Retrieve the list of supported universities from the Vault service.

    Returns:
        list: A list of university dictionaries from the Vault service.

    Raises:
        VaultServiceError: If the Vault service is unavailable or returns an error.
    """
    vault_url = getattr(settings, "VAULT_SERVICE_URL", "http://localhost:8004")
    vault_token = getattr(settings, "VAULT_TOKEN", "")

    if not vault_url:
        raise VaultServiceError("VAULT_SERVICE_URL is not configured")

    if not vault_token:
        raise VaultServiceError("VAULT_TOKEN is not configured")

    url = f"{vault_url.rstrip('/')}/universities"
    headers = {
        "X-Vault-Token": vault_token,
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=VAULT_TIMEOUT,
        )
    except requests.ConnectionError:
        logger.error(f"Failed to connect to Vault service at {vault_url}")
        raise VaultServiceError(
            "Unable to connect to the Vault service. Please try again later.",
            status_code=503,
        )
    except requests.Timeout:
        logger.error(f"Vault service request timed out ({VAULT_TIMEOUT}s)")
        raise VaultServiceError(
            "Vault service request timed out. Please try again later.",
            status_code=504,
        )
    except requests.RequestException as e:
        logger.error(f"Vault service request failed: {e}")
        raise VaultServiceError(
            "An error occurred while communicating with the Vault service.",
            status_code=502,
        )

    # Handle response status codes
    if response.status_code == 200:
        data = response.json()
        universities = data.get("universities", [])
        logger.info(f"Retrieved {len(universities)} universities from Vault")
        return universities

    # Unexpected status code
    detail = _extract_detail(response)
    logger.error(
        f"Unexpected Vault response {response.status_code} when fetching universities: {detail}"
    )
    raise VaultServiceError(
        f"Vault service returned an unexpected error: {detail or response.status_code}",
        status_code=response.status_code,
    )


def _extract_detail(response: requests.Response) -> str:
    """Extract error detail from a Vault service response."""
    try:
        data = response.json()
        return data.get("detail", "")
    except ValueError:
        return response.text[:200] if response.text else ""
