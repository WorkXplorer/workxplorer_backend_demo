"""
Custom DRF renderer that wraps ALL API responses in the standardized format.

This ensures consistency across the entire platform without needing to modify
every individual view. Views that already use APIResponse are detected and
not double-wrapped.

Success format:
{
    "success": true,
    "message": "...",
    "data": {...},
    "timestamp": "..."
}

Paginated format:
{
    "success": true,
    "message": "Data retrieved successfully",
    "data": [...],
    "pagination": {"count": ..., "next": ..., "previous": ..., ...},
    "timestamp": "..."
}

Error format:
{
    "success": false,
    "error": {"code": "...", "message": "...", "details": ...},
    "timestamp": "..."
}
"""
from datetime import datetime, timezone

from django.utils.translation import gettext as _
from rest_framework.renderers import JSONRenderer


class StandardJSONRenderer(JSONRenderer):
    """
    Custom renderer that wraps all DRF responses in the WorkXplorer
    standardized response format.

    - Already-standardized responses (with 'success' key) pass through unchanged.
    - Paginated responses are restructured with data + pagination keys.
    - Error responses (4xx/5xx) are wrapped in the error format.
    - Success responses are wrapped in the success format.
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None

        # If data is None (e.g., 204 No Content), let DRF handle it
        if data is None:
            return super().render(data, accepted_media_type, renderer_context)

        # If response is already in standardized format, pass through unchanged
        if isinstance(data, dict) and "success" in data:
            return super().render(data, accepted_media_type, renderer_context)

        status_code = response.status_code if response else 200

        if status_code >= 400:
            wrapped = self._wrap_error(data, status_code)
        else:
            wrapped = self._wrap_success(data, status_code)

        return super().render(wrapped, accepted_media_type, renderer_context)

    def _wrap_success(self, data, status_code):
        """Wrap a success response in standardized format."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # Detect paginated responses (LimitOffset or PageNumber pagination)
        if isinstance(data, dict) and "results" in data and "count" in data:
            pagination = {
                "count": data.get("count"),
                "next": data.get("next"),
                "previous": data.get("previous"),
            }
            # Include limit/offset if present (LimitOffsetPagination)
            if "limit" in data:
                pagination["limit"] = data["limit"]
            if "offset" in data:
                pagination["offset"] = data["offset"]

            return {
                "success": True,
                "message": _("Data retrieved successfully"),
                "data": data["results"],
                "pagination": pagination,
                "timestamp": timestamp,
            }

        # Detect message from common ad-hoc patterns (without mutating data)
        message = _("Operation completed successfully")
        response_data = data

        if isinstance(data, dict):
            # Extract message from common patterns - work on a copy to avoid mutation
            if "message" in data and len(data) <= 3:
                data_copy = dict(data)
                message = data_copy.pop("message", message)
                # If only message was in the dict, use the remaining data
                if not data_copy:
                    response_data = None
                else:
                    # Keep the structure stable - don't unwrap single keys
                    response_data = data_copy

        default_msg = _("Operation completed successfully")
        status_msg = {
            200: message,
            201: _("Resource created successfully") if message == default_msg else message,
            202: _("Request accepted") if message == default_msg else message,
        }

        return {
            "success": True,
            "message": status_msg.get(status_code, message),
            "data": response_data,
            "timestamp": timestamp,
        }

    def _wrap_error(self, data, status_code):
        """Wrap an error response in standardized format."""
        timestamp = datetime.now(timezone.utc).isoformat()
        error_code = self._get_error_code(status_code)
        message = _("An error occurred")
        details = None
        field_errors = None

        if isinstance(data, dict):
            # Extract message from common error patterns
            message = (
                    data.get("message")
                    or data.get("detail")
                    or data.get("error")
                    or message
            )
            if isinstance(message, list):
                message = message[0] if message else _("An error occurred")
            message = str(message)

            # Extract field errors (DRF validation format)
            remaining = {
                k: v
                for k, v in data.items()
                if k not in ("message", "detail", "error", "error_type", "non_field_errors")
            }
            if remaining and all(isinstance(v, list) for v in remaining.values()):
                field_errors = remaining
            elif remaining:
                details = remaining

            # Handle non_field_errors
            non_field = data.get("non_field_errors")
            if non_field:
                if not details:
                    details = non_field
                else:
                    details = {"non_field_errors": non_field, **(details if isinstance(details, dict) else {})}

        elif isinstance(data, list):
            # List of errors (e.g., non-field validation errors)
            if len(data) == 1:
                message = str(data[0])
            else:
                details = [str(e) for e in data]
        elif isinstance(data, str):
            message = data

        error_data = {
            "code": error_code,
            "message": message,
        }
        if details is not None:
            error_data["details"] = details
        if field_errors:
            error_data["field_errors"] = field_errors

        return {
            "success": False,
            "error": error_data,
            "timestamp": timestamp,
        }

    @staticmethod
    def _get_error_code(status_code):
        """Map HTTP status code to error code string."""
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            429: "RATE_LIMIT_EXCEEDED",
            500: "INTERNAL_SERVER_ERROR",
            502: "BAD_GATEWAY",
            503: "SERVICE_UNAVAILABLE",
        }
        return code_map.get(status_code, "UNKNOWN_ERROR")
