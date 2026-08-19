import os

from config.settings.components.apps import _env_bool
from .base import *
from .env_loader import env_loader

# Validate all required production variables
env_loader.validate_required_vars("production")

SECRET_KEY = env_loader.get_env("SECRET_KEY", required=True)
DEBUG = False

ALLOWED_HOSTS = [
    "workxplorer.uz",
    ".workxplorer.uz",
    "localhost",
    "127.0.0.1",
    # The Telegram bot's /report command. The bot runs on a Docker bridge
    # network while this backend uses host networking, so it reaches us through
    # the host rather than loopback and sends one of these as the Host header.
    # Neither is reachable from outside the machine.
    "host.docker.internal",
    "172.17.0.1",
]

# Remove development apps
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in DEVELOPMENT_APPS]

# Remove debug toolbar middleware
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]

# Add whitenoise middleware if available
try:
    import whitenoise

    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    # Static files configuration for production with whitenoise
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"



except ImportError:
    # Fallback to default static file handling
    pass

# CORS settings for production
CORS_ALLOWED_ORIGINS = [
    "https://workxplorer.uz",
    "https://app.workxplorer.uz",
    "https://dev.workxplorer.uz",
    "http://localhost:3000",
    "https://localhost:3000",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-refresh-token",
    "x-timezone",
]

CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# Security settings for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True  # Set to True when using HTTPS
CSRF_COOKIE_SECURE = True  # Set to True when using HTTPS
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "None"
SECURE_SSL_REDIRECT = True  # False для development, True для production
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# The chat gateway calls these endpoints over loopback, where there is no
# nginx to set X-Forwarded-Proto — so Django sees a plain HTTP request and
# redirects it to https://127.0.0.1:8001, which gunicorn does not speak. The
# caller then hangs on a TLS handshake that will never complete, and the
# worker on this side sits parsing a ClientHello as an HTTP request line until
# it gives up. A handful of those is enough to exhaust a sync worker pool and
# stall the entire site.
#
# Exempting them is safe: they never reach a browser, they carry no cookies,
# and they are authenticated by a shared service key rather than a session.
# The listener they arrive on is bound to loopback.
SECURE_REDIRECT_EXEMPT = [
    r"^api/v1/conversations/internal/",
]

CLAMAV_SCAN_ENABLED = _env_bool("CLAMAV_SCAN_ENABLED", "true")

# Static files configuration for production
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Database configuration for production
try:
    import dj_database_url

    if env_loader.get_env("DATABASE_URL"):
        DATABASES["default"] = dj_database_url.parse(
            env_loader.get_env("DATABASE_URL"),
            conn_max_age=600,
        )
except ImportError:
    # Use existing database configuration
    pass

# Simplified logging for production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "drf_spectacular": {
            "handlers": ["console"],
            "level": "CRITICAL",
            "propagate": False,
        },
    },
}