import os

# Determine current environment
environment = os.getenv("DJANGO_ENVIRONMENT", "development")

# REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/day",
        "user": "10000/day",
        "ai_revaluation": "30/hour",
        "ai_action": "10/hour",
        "skill_test": "30/hour",
        "resume_generation": "3/minute",
        # One ticket per WebSocket connection. Generous enough for a client
        # riding out a flaky network with backoff, tight enough to cap a
        # client stuck in a reconnect loop.
        "chat_ticket": "120/hour",
    },
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.authentication.services.authentication.CookieJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.CustomPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "core.renderers.StandardJSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",  # Enable for dev/testing
    ],
    "EXCEPTION_HANDLER": "apps.authentication.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

if environment == "production":
    # In production, only use StandardJSONRenderer (no browsable API)
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
        "core.renderers.StandardJSONRenderer",
    ]

# Spectacular settings for API documentation
SPECTACULAR_SETTINGS = {
    "TITLE": "WorkXplorer API",
    "DESCRIPTION": "API documentation for WorkXplorer backend",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "DISABLE_ERRORS_AND_WARNINGS": True,
    "POSTPROCESSING_HOOKS": [
        "core.schema.postprocess_schema_responses",
    ],
}