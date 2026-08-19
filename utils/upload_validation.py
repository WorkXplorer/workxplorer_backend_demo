import logging

from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

from utils.virus_scanner import (
    VirusScanError,
    FileInfectedError,
    ScanUnavailableError,
    scan_uploaded_file,
)
logger = logging.getLogger(__name__)


def validate_uploaded_file(value, allow_string: bool = False):
    """
    Validate an uploaded file with antivirus scanning.

    Maps structured VirusScanError subclasses to translated, user-facing
    serializers.ValidationError messages instead of leaking raw English
    scanner strings to the API client.

    Args:
        value: Uploaded file, None, or optionally a string path.
        allow_string: When True, string values are passed through unchanged.

    Returns:
        The original value when validation passes.

    Raises:
        serializers.ValidationError: With a translated message on failure.
    """
    if value is None:
        return value

    if isinstance(value, str):
        if allow_string:
            return value
        raise serializers.ValidationError(
            _("String values are not allowed for this field.")
        )

    try:
        scan_uploaded_file(value)
    except FileInfectedError:
        logger.error("Uploaded file is infected.", exc_info=True)
        raise serializers.ValidationError(
            _("Malicious content was detected in the uploaded file")
        )
    except ScanUnavailableError:
        logger.error("Antivirus service is temporarily unavailable.", exc_info=True)
        raise serializers.ValidationError(
            _("The antivirus service is temporarily unavailable. Please try again later.")
        )
    except VirusScanError:
        logger.error("Virus scan failed for uploaded file.", exc_info=True)
        raise serializers.ValidationError(
             _("Malicious content was detected in the uploaded file.")
         )
    return value
