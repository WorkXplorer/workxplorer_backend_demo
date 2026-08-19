# middleware/input_validation.py
import json
import re
import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger(__name__)


class InputValidationMiddleware(MiddlewareMixin):
    """
    Middleware for simple input validation (anti-SQLi, XSS, command injection)
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Pre-compile regex patterns for performance
        # Note: keep patterns conservative to reduce false positives
        self.security_patterns = {
            "sql_injection": [
                # more restrictive: look for common SQL patterns with word boundaries
                re.compile(r"(?i)\bunion\b\s+\bselect\b"),
                re.compile(r"(?i)\bselect\b.+\bfrom\b"),
                re.compile(r"(?i)'\s*or\s*'1'='1'"),
                # Detect common boolean-based blind injection patterns
                re.compile(r"(?i)\b(and|or)\b\s+\d+\s*=\s*\d+"),
                # Detect tautologies like ' and '2167'='2167
                re.compile(r"(?i)'\s*(and|or)\s*'\d+'\s*=\s*'\d+"),
                # Detect comment-based termination: -- or #
                re.compile(r"(?i)\b(and|or)\b\s+\d+\s*=\s*0?\d+\s*--"),
                # Detect stacked queries
                re.compile(r";\s*(drop|alter|create|insert|update|delete)\b", re.IGNORECASE),
            ],
            "xss": [
                re.compile(r"(?i)<\s*script[^>]*>"),
                re.compile(r"(?i)javascript\s*:", re.IGNORECASE),
                re.compile(
                    r"(?i)on(error|load|click|mouseover|focus|blur|change|toggle|"
                    r"pageshow|scroll|wheel|pointer|animation|transition)\s*=",
                    re.IGNORECASE,
                ),
            ],
            "command_injection": [
                re.compile(r"(?i);\s*(rm|cat|curl|wget)\b"),
                re.compile(r"(?i)\$\(.+?\)|`.+?`"),
            ],
            "path_traversal": [
                # Detect ../ and ..\ sequences (URL-decoded and raw)
                re.compile(r"(\.\.[\\/]){2,}"),
                # Detect direct /etc/passwd or /etc/shadow access
                re.compile(r"(?i)/etc/(passwd|shadow|hosts)"),
                # Detect null byte injection
                re.compile(r"\x00|%00|\\u0000"),
                # Detect absolute path references to system dirs
                re.compile(r"(?i)^/+(etc|var|usr|tmp|proc|sys)/"),
            ],
        }

        # Basic limits
        self.max_length = getattr(settings, "VALIDATION_MAX_LENGTH", 10000)
        self.max_depth = getattr(settings, "VALIDATION_MAX_DEPTH", 20)

        super().__init__(get_response)

    def __call__(self, request):
        # Skip validation for certain paths (include swagger/schema)
        if self.should_skip_validation(request):
            return self.get_response(request)

        validation_result = self.validate_request(request)
        if validation_result:
            return validation_result

        return self.get_response(request)

    def should_skip_validation(self, request):
        """
        Skip validation for admin, static files, swagger/schema endpoints, media, etc.
        """
        skip_paths = getattr(
            settings,
            "VALIDATION_SKIP_PATHS",
            [
                "/admin/",
                "/static/",
                "/media/",
                "/swagger",  # swagger UI
                "/swagger/",  # swagger UI
                "/redoc",  # redoc UI
                "/redoc/",  # redoc UI
                "/api/schema",  # drf-spectacular schema endpoint
                "/api/schema/",  # schema with trailing slash
            ],
        )
        # Also skip if this is an internal schema content-type request
        content_type = (request.content_type or "").lower()
        if "application/schema+json" in content_type:
            return True

        return any(request.path.startswith(path) for path in skip_paths)

    def validate_request(self, request):
        errors = []

        try:
            # Validate query parameters, but skip typical swagger params by name (e.g., "swagger", "format")
            for key, value in request.GET.items():
                if self._is_schema_like_param(key):
                    continue
                errors.extend(self.check_security_patterns(key, value))

            # Validate security-sensitive HTTP headers (e.g., Referer, X-Forwarded-For)
            sensitive_headers = ["HTTP_REFERER", "HTTP_X_FORWARDED_FOR", "HTTP_X_FORWARDED_HOST"]
            for header in sensitive_headers:
                value = request.META.get(header, "")
                if value:
                    errors.extend(self.check_security_patterns(header, value))

            # Validate form data for POST/PUT/PATCH
            if request.method in ["POST", "PUT", "PATCH"]:
                for key, value in request.POST.items():
                    if self._is_schema_like_param(key):
                        continue
                    if key in request.FILES:
                        continue
                    errors.extend(self.check_security_patterns(key, value))

                # JSON body
                if (
                        request.content_type
                        and "application/json" in request.content_type.lower()
                ):
                    body = self.get_cached_body(request)
                    if body:
                        json_errors = self.validate_json_body(body)
                        errors.extend(json_errors)

        except Exception as e:
            logger.exception(f"Validation error: {str(e)}")
            errors.append("Validation failed")

        if errors:
            return JsonResponse(
                {"error": True, "message": "Input validation failed", "errors": errors},
                status=400,
            )

        return None

    def _is_schema_like_param(self, key):
        # skip swagger/drf-spectacular typical params (customize if needed)
        schema_like = {"format", "swagger", "schema", "pretty"}
        return str(key).lower() in schema_like

    def get_cached_body(self, request):
        """
        Ensure request.body is cached so view can reuse it
        """
        if not hasattr(request, "_cached_body"):
            try:
                request._cached_body = request.body
            except Exception:
                request._cached_body = b""
        return request._cached_body

    def validate_json_body(self, body):
        errors = []
        try:
            json_data = json.loads(body.decode("utf-8"))
            errors.extend(self.validate_json_data(json_data))
        except json.JSONDecodeError:
            # avoid blocking non-JSON bodies (but this branch shouldn't be reached
            # because we check content_type earlier)
            errors.append("Invalid JSON format")
        except UnicodeDecodeError:
            errors.append("Invalid encoding")
        return errors

    def validate_json_data(self, data, path="root", depth=0):
        errors = []
        if depth > self.max_depth:
            return ["JSON nesting too deep"]

        if isinstance(data, dict):
            if len(data) > 50:
                errors.append("Too many JSON keys")
            for key, value in data.items():
                # skip schema/meta keys commonly used by docs
                if str(key).lower() in ("example", "description", "title", "help_text"):
                    # still optionally validate length but skip heavy pattern checks
                    if isinstance(value, str) and len(value) > self.max_length:
                        errors.append(f"String too long at {path}.{key}")
                    continue
                errors.extend(self.check_security_patterns(key, key))
                errors.extend(
                    self.validate_json_data(value, f"{path}.{key}", depth + 1)
                )

        elif isinstance(data, list):
            if len(data) > 100:
                errors.append("Array too large")
            for item in data:
                errors.extend(self.validate_json_data(item, path, depth + 1))

        elif isinstance(data, str):
            if len(data) > self.max_length:
                errors.append(f"String too long at {path}")
            errors.extend(self.check_security_patterns(path, data))

        return errors

    def check_security_patterns(self, field_name, value):
        errors = []
        value_str = str(value)

        if len(value_str) > self.max_length:
            errors.append(f"Field '{field_name}' too long")
            return errors

        for threat_type, patterns in self.security_patterns.items():
            for pattern in patterns:
                if pattern.search(value_str):
                    logger.warning(
                        f"Security threat: {threat_type} in {field_name} (value starts: {value_str[:50]!r})"
                    )
                    errors.append("Invalid input detected")
                    return errors  # stop on first match

        return errors
