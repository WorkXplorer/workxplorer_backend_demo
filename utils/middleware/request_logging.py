import logging
import time
import json
from utils.logging_config import setup_request_logger, setup_category_loggers, get_log_category
from django.http.request import RawPostDataException
from django.core.exceptions import RequestDataTooBig

request_logger = setup_request_logger()
category_loggers = setup_category_loggers()
logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """Middleware to log all API requests with detailed information.

    Logs to:
    - Global requests log (all requests)
    - Category-specific logs (vacancies, custom_users, companies, applications)
    """

    SENSITIVE_KEYS = {"password", "token", "secret", "access", "refresh", "credit_card", "confirm_password"}

    def __init__(self, get_response):
        self.get_response = get_response

    def _sanitize(self, data):
        """Mask sensitive fields in request/response payloads."""
        if isinstance(data, dict):
            return {
                k: "***" if k.lower() in self.SENSITIVE_KEYS else self._sanitize(v)
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [self._sanitize(item) for item in data]
        return data

    def _get_request_body(self, request):
        """Extract and parse request body safely."""
        try:
            # Check if this is a multipart/form-data request (file upload)
            content_type = request.META.get('CONTENT_TYPE', '')
            if 'multipart/form-data' in content_type:
                return "<file-upload>"
            
            # Check content length before reading body
            content_length = request.META.get('CONTENT_LENGTH')
            if content_length:
                try:
                    # Skip logging large requests (> 1MB)
                    if int(content_length) > 1024 * 1024:
                        return f"<large-request-{content_length}-bytes>"
                except (ValueError, TypeError):
                    logger.warning(f"Invalid CONTENT_LENGTH: {content_length}")
            
            raw_body = request.body
            if raw_body:
                try:
                    return json.loads(raw_body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return "<non-json>"
            return {}
        except RawPostDataException:
            return "<body-unavailable>"
        except RequestDataTooBig:
            return "<request-too-large>"

    def _get_response_body(self, response):
        """Extract and parse response body safely."""
        if hasattr(response, "content"):
            try:
                return json.loads(response.content.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return "<non-json>"
        return {}

    def _format_log_message(self, request, response, request_body, response_body, response_time, user_id):
        """Build the log message string."""
        resp_str = (
            json.dumps(response_body, ensure_ascii=False)
            if isinstance(response_body, (dict, list))
            else response_body
        )
        return (
            f"{request.method} | {request.path} | {response.status_code} | "
            f"{response_time} | user_id={user_id} | "
            f"request={json.dumps(request_body, ensure_ascii=False)} | "
            f"response={resp_str}"
        )

    def __call__(self, request):
        start_time = time.time()

        request_body = self._get_request_body(request)

        response = self.get_response(request)

        # Get user_id AFTER response generation (so DRF JWT auth has run)
        user_id = None
        if hasattr(request, "user") and request.user and request.user.is_authenticated:
            user_id = getattr(request.user, "id", None)

        response_time = f"{(time.time() - start_time) * 1000:.2f}ms"

        response_body = self._get_response_body(response)

        # Sanitize payloads before logging
        safe_request = self._sanitize(request_body) if isinstance(request_body, (dict, list)) else request_body
        safe_response = self._sanitize(response_body) if isinstance(response_body, (dict, list)) else response_body

        log_message = self._format_log_message(
            request, response, safe_request, safe_response, response_time, user_id
        )

        # Determine log level based on status code
        is_error = response.status_code >= 400

        # Always log to global logger
        if is_error:
            request_logger.error(log_message)
        else:
            request_logger.info(log_message)

        # Log to category-specific logger if path matches
        category = get_log_category(request.path)
        if category and category in category_loggers:
            cat_logger = category_loggers[category]
            if is_error:
                cat_logger.error(log_message)
            else:
                cat_logger.info(log_message)

        return response
