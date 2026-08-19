import logging
from datetime import datetime, timezone

from django.http import Http404, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError, PermissionDenied
from rest_framework.exceptions import APIException

from core.responses import ErrorCodes

logger = logging.getLogger(__name__)


class GlobalErrorHandlingMiddleware(MiddlewareMixin):
    """
    Enhanced global error handling middleware for WorkXplorer Platform.

    Security: Always returns safe JSON responses for API endpoints.
    Never exposes stack traces, database credentials, file paths, or
    environment variables — even when DEBUG=True.
    """

    def process_exception(self, request, exception):
        """Handle exceptions that aren't caught by DRF"""

        # Let DRF handle API exceptions through its own exception handler
        if isinstance(exception, APIException):
            return None

        # Log the exception with detailed information
        self._log_exception(request, exception)

        # Only handle API requests (check for /api/ in path)
        if not self._is_api_request(request):
            return None

        return self._create_error_response(request, exception)

    def _log_exception(self, request, exception):
        """Log exception with request context"""
        logger.error(
            f"Unhandled Exception: {type(exception).__name__}: {str(exception)}",
            exc_info=True,
            extra={
                "request_path": request.path,
                "request_method": request.method,
                "user_id": (
                    getattr(request.user, "id", None)
                    if hasattr(request, "user")
                    else None
                ),
                "user_email": (
                    getattr(request.user, "email", None)
                    if hasattr(request, "user")
                    else None
                ),
                "ip_address": self._get_client_ip(request),
                "user_agent": request.headers.get('User-Agent', '') if request else '',
                "exception_type": type(exception).__name__,
            },
        )

    def _create_error_response(self, request, exception):
        """Create standardized error response based on exception type"""

        # Handle Django core exceptions
        if isinstance(exception, ValidationError):
            return self._handle_django_validation_error(exception)

        elif isinstance(exception, PermissionDenied):
            return self._json_error_response(
                code=ErrorCodes.FORBIDDEN,
                message=_("Access denied"),
                details=_("You do not have permission to perform this action"),
                status_code=403,
            )

        elif isinstance(exception, Http404):
            return self._json_error_response(
                code="NOT_FOUND",
                message=_("Resource not found"),
                details=_("The requested resource does not exist or has been deleted"),
                status_code=404,
            )

        elif isinstance(exception, ValueError):
            return self._json_error_response(
                code="VALIDATION_ERROR",
                message=_("Invalid value provided"),
                details=str(exception),
                status_code=400,
            )

        elif isinstance(exception, KeyError):
            return self._json_error_response(
                code="VALIDATION_ERROR",
                message=_("Required field missing"),
                details=_("Missing field: %(field)s") % {"field": str(exception)},
                status_code=400,
            )

        elif isinstance(exception, AttributeError):
            return self._safe_server_error_response()

        # Handle database-related exceptions
        elif "psycopg2" in str(type(exception)) or "django.db" in str(type(exception)):
            logger.error(f"Database error: {exception}")
            return self._safe_server_error_response(
                message=_("Database operation failed"),
            )

        # Default server error — NEVER expose debug info on API endpoints
        return self._safe_server_error_response()

    def _handle_django_validation_error(self, exception):
        """Handle Django ValidationError"""
        details = None
        field_errors = None

        if hasattr(exception, "message_dict"):
            field_errors = exception.message_dict
        elif hasattr(exception, "messages"):
            details = list(exception.messages)
        else:
            details = str(exception)

        error_data = {
            "code": "VALIDATION_ERROR",
            "message": _("Validation failed"),
        }
        if details is not None:
            error_data["details"] = details
        if field_errors:
            error_data["field_errors"] = field_errors

        return JsonResponse(
            {
                "success": False,
                "error": error_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=400,
        )

    def _json_error_response(self, code, message, details=None, status_code=400):
        """
        Return a standardized JSON error response.
        Used for non-DRF exceptions caught by this middleware.
        """
        error_data = {
            "code": code,
            "message": message,
        }
        if details is not None:
            error_data["details"] = details

        return JsonResponse(
            {
                "success": False,
                "error": error_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            status=status_code,
        )

    def _safe_server_error_response(self, message=""):
        """
        Return a safe JSON error response that never leaks sensitive information.

        This is used for ALL unhandled exceptions on API endpoints, regardless
        of the DEBUG setting. Debug information should only be inspected via
        server-side logs, never sent to the client.
        """
        error_data = {
            "success": False,
            "error": {
                "code": ErrorCodes.INTERNAL_SERVER_ERROR,
                "message": message or _("An unexpected error occurred"),
                "details": _("Please contact support if this issue persists"),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return JsonResponse(error_data, status=500)

    def _is_api_request(self, request):
        """Check if request is to an API endpoint"""
        return request.path.startswith("/api/")

    def _get_client_ip(self, request):
        """Extract client IP address"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "Unknown")
        return ip
