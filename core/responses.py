from rest_framework.response import Response
from rest_framework import status
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List, Union

from django.utils.translation import gettext as _


class APIResponse:
    """
    Standardized API response format for WorkXplorer Platform

    Success Response Format:
    {
        "success": true,
        "message": "Operation completed successfully",
        "data": {...},
        "timestamp": "2024-01-15T10:30:00Z"
    }

    Error Response Format:
    {
        "success": false,
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid input provided",
            "details": {...},
            "field_errors": {...}
        },
        "timestamp": "2024-01-15T10:30:00Z"
    }
    """

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format"""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def success(
            data: Any = None,
            message: str = "",
            status_code: int = status.HTTP_200_OK,
            pagination: Optional[Dict] = None,
    ) -> Response:
        """
        Standard success response

        Args:
            data: Response data
            message: Success message
            status_code: HTTP status code
            pagination: Pagination info for list responses
        """
        response_data = {
            "success": True,
            "message": message or _("Operation completed successfully"),
            "timestamp": APIResponse._get_timestamp(),
        }

        if data is not None:
            response_data["data"] = data

        if pagination:
            response_data["pagination"] = pagination

        return Response(response_data, status=status_code)

    @staticmethod
    def error(
            message: str = "",
            code: str = "UNKNOWN_ERROR",
            details: Optional[Union[str, Dict, List]] = None,
            field_errors: Optional[Dict] = None,
            status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> Response:
        """
        Standard error response

        Args:
            message: Error message
            code: Error code for client handling
            details: Additional error details
            field_errors: Field-specific validation errors
            status_code: HTTP status code
        """
        error_data = {"code": code, "message": message or _("An error occurred")}

        if details is not None:
            error_data["details"] = details

        if field_errors:
            error_data["field_errors"] = field_errors

        response_data = {
            "success": False,
            "error": error_data,
            "timestamp": APIResponse._get_timestamp(),
        }

        return Response(response_data, status=status_code)

    @staticmethod
    def validation_error(
            message: str = "",
            field_errors: Optional[Dict] = None,
            details: Optional[Union[str, Dict]] = None,
    ) -> Response:
        """Validation error response"""
        return APIResponse.error(
            message=message or _("Validation failed"),
            code="VALIDATION_ERROR",
            details=details,
            field_errors=field_errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @staticmethod
    def not_found(
            message: str = "", resource: str = ""
    ) -> Response:
        """Not found error response"""
        return APIResponse.error(
            message=message or _("Resource not found"),
            code="NOT_FOUND",
            details=_("%(resource)s does not exist or has been deleted") % {"resource": resource or _("Resource")},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    @staticmethod
    def unauthorized(
            message: str = "",
            details: str = "",
    ) -> Response:
        """Unauthorized error response"""
        return APIResponse.error(
            message=message or _("Authentication required"),
            code="UNAUTHORIZED",
            details=details or _("Valid authentication credentials must be provided"),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    @staticmethod
    def forbidden(
            message: str = "",
            details: str = "",
    ) -> Response:
        """Forbidden error response"""
        return APIResponse.error(
            message=message or _("Access denied"),
            code="FORBIDDEN",
            details=details or _("You do not have permission to perform this action"),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    @staticmethod
    def conflict(
            message: str = "", details: Optional[Union[str, Dict]] = None
    ) -> Response:
        """Conflict error response"""
        return APIResponse.error(
            message=message or _("Resource conflict"),
            code="CONFLICT",
            details=details
                    or _("The resource already exists or conflicts with existing data"),
            status_code=status.HTTP_409_CONFLICT,
        )

    @staticmethod
    def server_error(
            message: str = "", details: Optional[str] = None
    ) -> Response:
        """Server error response"""
        return APIResponse.error(
            message=message or _("Internal server error"),
            code="INTERNAL_SERVER_ERROR",
            details=details or _("An unexpected error occurred on the server"),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @staticmethod
    def bad_request(
            message: str = "",
            details: Optional[Union[str, Dict]] = None,
            field_errors: Optional[Dict] = None,
    ) -> Response:
        """Bad request error response"""
        return APIResponse.error(
            message=message or _("Bad request"),
            code="BAD_REQUEST",
            details=details,
            field_errors=field_errors,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @staticmethod
    def created(
            data: Any = None, message: str = ""
    ) -> Response:
        """Created response"""
        return APIResponse.success(
            data=data, message=message or _("Resource created successfully"), status_code=status.HTTP_201_CREATED
        )

    @staticmethod
    def no_content(message: str = "") -> Response:
        """No content response"""
        return APIResponse.success(
            message=message or _("Operation completed successfully"), status_code=status.HTTP_204_NO_CONTENT
        )


class PaginatedAPIResponse:
    """Helper for paginated responses"""

    @staticmethod
    def create(
            data: List,
            count: int,
            page: int,
            page_size: int,
            message: str = "",
    ) -> Response:
        """Create paginated response"""
        pagination = {
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": (count + page_size - 1) // page_size,
            "has_next": page * page_size < count,
            "has_previous": page > 1,
        }

        return APIResponse.success(
            data=data,
            message=message or _("Data retrieved successfully"),
            pagination=pagination
        )


# Error codes for consistent client-side handling
class ErrorCodes:
    """Standard error codes for the WorkXplorer platform"""

    # Authentication & Authorization
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    WRONG_USER_TYPE = "WRONG_USER_TYPE"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_REQUIRED = "TOKEN_REQUIRED"

    # Validation
    VALIDATION_ERROR = "VALIDATION_ERROR"
    REQUIRED_FIELD = "REQUIRED_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_CHOICE = "INVALID_CHOICE"

    # Resources
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    ALREADY_EXISTS = "ALREADY_EXISTS"

    # Business Logic
    PERMISSION_DENIED = "PERMISSION_DENIED"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"

    # Server Errors
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"

    # Job Board Specific
    APPLICATION_ALREADY_EXISTS = "APPLICATION_ALREADY_EXISTS"
    VACANCY_INACTIVE = "VACANCY_INACTIVE"
    RESUME_REQUIRED = "RESUME_REQUIRED"
    COMPANY_NOT_ACTIVE = "COMPANY_NOT_ACTIVE"
    RECRUITER_MISSING_COMPANY = "RECRUITER_MISSING_COMPANY"

    # Unknown Errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
