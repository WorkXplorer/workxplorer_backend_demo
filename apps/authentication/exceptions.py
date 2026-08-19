from rest_framework.views import exception_handler
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import (
    ValidationError,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    NotFound,
    MethodNotAllowed,
    Throttled,
)
import logging

from django.utils.translation import gettext as _
from core.responses import APIResponse, ErrorCodes

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns consistent error responses
    """
    request = context.get("request")

    # Log the exception
    if request:
        logger.error(
            f"API Exception: {type(exc).__name__}: {str(exc)}",
            extra={
                "request_path": request.path,
                "request_method": request.method,
                "user": getattr(request, "user", "Anonymous"),
                "exception_type": type(exc).__name__,
            },
        )

    # Handle DRF exceptions
    if isinstance(exc, ValidationError):
        return handle_validation_error(exc)

    elif isinstance(exc, NotAuthenticated):
        return APIResponse.unauthorized(
            message=_("Authentication required"),
            details=_("Authentication credentials were not provided"),
        )

    elif isinstance(exc, AuthenticationFailed):
        return handle_authentication_error(exc, request)

    elif isinstance(exc, PermissionDenied):
        detail = exc.detail if hasattr(exc, "detail") else str(exc)
        has_custom_message = bool(detail) and str(detail) != "You do not have permission to perform this action."
        return APIResponse.forbidden(
            message=str(detail) if has_custom_message else _("Access denied"),
            details=(
                str(detail)
                if detail
                else _("You do not have permission to perform this action")
            ),
        )

    elif isinstance(exc, NotFound):
        return APIResponse.not_found(
            message=_("Resource not found"), resource=_("Requested resource")
        )

    elif isinstance(exc, MethodNotAllowed):
        return APIResponse.error(
            message=_("Method not allowed"),
            code="METHOD_NOT_ALLOWED",
            details=_("Method %(method)s is not allowed for this endpoint") % {
                "method": request.method if request else "Unknown"},
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    elif isinstance(exc, Throttled):
        return APIResponse.error(
            message=_("Too many requests"),
            code="RATE_LIMIT_EXCEEDED",
            details=_("Rate limit exceeded. Try again in %(seconds)s seconds") % {"seconds": exc.wait},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Handle Django exceptions
    elif isinstance(exc, Http404):
        return APIResponse.not_found()

    elif isinstance(exc, DjangoValidationError):
        return APIResponse.validation_error(
            message=_("Validation failed"), details=str(exc)
        )

    # Handle custom business exceptions
    elif hasattr(exc, "error_code"):
        return APIResponse.error(
            message=str(exc),
            code=getattr(exc, "error_code", ErrorCodes.UNKNOWN_ERROR),
            status_code=getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST),
        )

    # Fallback to default DRF handler
    response = exception_handler(exc, context)
    if response is not None:
        return APIResponse.error(
            message=_("An error occurred"),
            code=ErrorCodes.INTERNAL_SERVER_ERROR,
            details=response.data,
            status_code=response.status_code,
        )

    # Unhandled exceptions
    return APIResponse.server_error(
        message=_("An unexpected error occurred"),
        details=_("Please contact support if this issue persists"),
    )


def handle_validation_error(exc):
    """Handle DRF ValidationError with field-specific errors"""
    field_errors = {}
    general_errors = []

    if hasattr(exc, "detail"):
        if isinstance(exc.detail, dict):
            for field, errors in exc.detail.items():
                if isinstance(errors, list):
                    field_errors[field] = [str(error) for error in errors]
                else:
                    field_errors[field] = [str(errors)]
        elif isinstance(exc.detail, list):
            general_errors = [str(error) for error in exc.detail]
        else:
            general_errors = [str(exc.detail)]

    return APIResponse.validation_error(
        message=_("Validation failed"),
        field_errors=field_errors if field_errors else None,
        details=general_errors if general_errors else None,
    )


def handle_authentication_error(exc, request):
    """Handle authentication errors with custom messages"""
    # Extract clean, human-readable error message from exception detail
    if hasattr(exc, "detail"):
        if isinstance(exc.detail, dict):
            error_message = str(
                exc.detail.get("detail", exc.detail.get("message", _("Authentication failed")))
            )
        elif isinstance(exc.detail, list):
            error_message = str(exc.detail[0]) if exc.detail else str(exc)
        else:
            error_message = str(exc.detail)
    else:
        error_message = str(exc)

    # Customize messages for better UX
    message_mappings = {
        "Authentication credentials were not provided.": {
            "message": _("Authentication required"),
            "code": ErrorCodes.TOKEN_REQUIRED,
            "details": _("Please provide valid authentication credentials"),
        },
        "Given token not valid for any token type": {
            "message": _("Invalid authentication token"),
            "code": ErrorCodes.TOKEN_INVALID,
            "details": _("The provided token is invalid or malformed"),
        },
        "Token is invalid or expired": {
            "message": _("Authentication token expired"),
            "code": ErrorCodes.TOKEN_EXPIRED,
            "details": _("Your session has expired. Please log in again"),
        },
    }

    mapping = message_mappings.get(
        error_message,
        {
            "message": _("Authentication failed"),
            "code": ErrorCodes.UNAUTHORIZED,
            "details": error_message,
        },
    )

    return APIResponse.error(
        message=mapping["message"],
        code=mapping["code"],
        details=mapping["details"],
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


# Custom business exceptions
class BusinessException(Exception):
    """Base class for business logic exceptions"""

    def __init__(
            self,
            message,
            error_code=ErrorCodes.OPERATION_NOT_ALLOWED,
            status_code=status.HTTP_400_BAD_REQUEST,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)


class ApplicationExistsException(BusinessException):
    """Raised when candidate tries to apply to same vacancy twice"""

    def __init__(self, message=""):
        super().__init__(
            message=message or _("You have already applied to this vacancy"),
            error_code=ErrorCodes.APPLICATION_ALREADY_EXISTS,
            status_code=status.HTTP_409_CONFLICT,
        )


class VacancyInactiveException(BusinessException):
    """Raised when trying to apply to inactive vacancy"""

    def __init__(self, message=""):
        super().__init__(
            message=message or _("This vacancy is no longer active"),
            error_code=ErrorCodes.VACANCY_INACTIVE,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ResumeRequiredException(BusinessException):
    """Raised when resume is required but not provided"""

    def __init__(self, message=""):
        super().__init__(
            message=message or _("A resume is required to apply for this position"),
            error_code=ErrorCodes.RESUME_REQUIRED,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
