import json
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from utils.virus_scanner import (
    scan_uploaded_file,
    FileInfectedError,
    ScanUnavailableError,
    FileTooLargeError,
    InvalidFileTypeError,
)

# Import centralized constants from Django settings
MAX_FILE_SIZE = settings.MAX_FILE_SIZE
ALLOWED_EXTENSIONS = settings.ALLOWED_FILE_EXTENSIONS


def format_certificate_error(error: Exception, language: str) -> dict:
    """Map a VirusScanError (or any exception) to a structured error dict.

    Uses isinstance checks on the exception type instead of string parsing,
    so wording changes in the scanner layer never break categorization.
    """
    if isinstance(error, FileInfectedError):
        return {
            "code": "FILE_INFECTED",
            "message": _("Malicious content was detected in the uploaded file"),
            "details": str(_("Virus detected: {threat}")).format(threat=error.threat),
            "field_error": _("The file failed the security check."),
        }

    if isinstance(error, ScanUnavailableError):
        return {
            "code": "ANTIVIRUS_SCAN_FAILED",
            "message": _("The file security scan could not be completed"),
            "details": _("The antivirus service is temporarily unavailable. Please try again later."),
            "field_error": _("The file did not pass the antivirus check."),
        }

    if isinstance(error, FileTooLargeError):
        return {
            "code": "FILE_TOO_LARGE",
            "message": _("The file size exceeds the allowed limit"),
            "details": _("The file size must not exceed 5MB."),
            "field_error": _("The uploaded file is too large."),
        }

    if isinstance(error, InvalidFileTypeError):
        return {
            "code": "INVALID_FILE_TYPE",
            "message": _("The file type is not supported"),
            "details": str(_("Allowed formats: {allowed}.")).format(
                allowed=", ".join(ALLOWED_EXTENSIONS)
            ),
            "field_error": _("The uploaded file type is invalid."),
        }

    return {
        "code": "CERTIFICATE_FILE_INVALID",
        "message": _("An error occurred while validating the certificate file"),
        "details": _("Please verify the uploaded file and try again."),
        "field_error": _("The certificate file is invalid."),
    }


def build_certificate_error_payload(errors: list, language: str) -> dict:
    """Build a structured API error payload from a list of VirusScanError exceptions."""
    formatted_errors = [format_certificate_error(e, language) for e in errors]
    primary_error = formatted_errors[0] if formatted_errors else format_certificate_error(Exception(), language)
    details = [item["details"] for item in formatted_errors]
    return {
        "code": primary_error["code"],
        "message": primary_error["message"],
        "details": details[0] if len(details) == 1 else details,
        "field_errors": {
            "certificates": [item["field_error"] for item in formatted_errors]
        },
    }


def validate_certificate_file(file) -> None:
    """Validate a certificate file: antivirus scan, size, and extension.

    Always raises a VirusScanError subclass on failure — never returns
    an error string — so callers can catch and collect exceptions uniformly.

    Raises:
        FileInfectedError:    virus detected.
        ScanUnavailableError: antivirus service unavailable.
        FileTooLargeError:    file exceeds MAX_FILE_SIZE.
        InvalidFileTypeError: file extension not in ALLOWED_EXTENSIONS.
    """
    if file is None:
        return

    # Raises FileInfectedError / ScanUnavailableError on failure
    scan_uploaded_file(file)

    # Validate file size (max 5 MB)
    if file.size > MAX_FILE_SIZE:
        raise FileTooLargeError(
            f"File '{file.name}' exceeds 5MB limit "
            f"({file.size / (1024 * 1024):.2f} MB)"
        )

    # Validate file extension
    file_name = file.name.lower()
    extension = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(
            f"File '{file.name}' has invalid type '{extension}'. "
            f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )


def _inject_language_certificate_files(request, data):
    """
    Merge language certificate files from form-data into the language_certificates_data.

    Supports TWO formats:
    
    Format 1 (JSON + separate files):
    - language_certificates_data: JSON string with [{language_id, level, id?}, ...]
    - language_certificate_file_0, language_certificate_file_1, ...: uploaded files

    Format 2 (form-data array notation):
    - language_certificates_data[0][language_id]: 3
    - language_certificates_data[0][level]: B1
    - language_certificates_data[0][file]: (binary)
    
    DRF automatically parses Format 2 into a list of dicts, so we handle both.
    """
    lc_raw = data.get("language_certificates_data")
    
    # If not present, check if form-data sent it with array notation
    # DRF parsers may have already converted it to a list
    if lc_raw is None:
        # Check if any keys in request.data match the pattern language_certificates_data[n][field]
        # This shouldn't be needed as DRF parsers handle it, but as a fallback:
        lc_list = []
        idx = 0
        while True:
            lang_id = data.get(f"language_certificates_data[{idx}][language_id]")
            if lang_id is None:
                break
            
            item = {
                "language_id": lang_id,
                "level": data.get(f"language_certificates_data[{idx}][level]"),
            }
            
            # Check for file
            file_obj = request.FILES.get(f"language_certificates_data[{idx}][file]")
            if file_obj:
                item["file"] = file_obj
            
            # Check for optional id field (for updates)
            item_id = data.get(f"language_certificates_data[{idx}][id]")
            if item_id:
                item["id"] = item_id
            
            lc_list.append(item)
            idx += 1
        
        if lc_list:
            data["language_certificates_data"] = lc_list
            return data
        
        return data

    # Parse JSON string if needed (Format 1)
    if isinstance(lc_raw, str):
        try:
            lc_list = json.loads(lc_raw) if lc_raw.strip() else []
        except json.JSONDecodeError:
            return data
    elif isinstance(lc_raw, list):
        # Already parsed by DRF (could be Format 2 or Format 1 with JSON body)
        lc_list = lc_raw
    else:
        return data

    # Ensure all items are dicts
    lc_list = [item for item in lc_list if isinstance(item, dict)]

    # Attach files by index (Format 1 - separate file fields)
    for idx, item in enumerate(lc_list):
        if "file" not in item:
            file_key = f"language_certificate_file_{idx}"
            file_obj = request.FILES.get(file_key)
            if file_obj:
                item["file"] = file_obj

    data["language_certificates_data"] = lc_list
    return data
