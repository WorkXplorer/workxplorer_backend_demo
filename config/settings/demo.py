import os
from .base import *
from .env_loader import env_loader

# Validate required environment variables for demo
env_loader.validate_required_vars("demo")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env_loader.get_env("SECRET_KEY", required=True)

# Demo should have DEBUG=False like production for realistic testing
DEBUG = False

# Allow demo domains
ALLOWED_HOSTS = [
    "api-demo.workxplorer.uz",
    "demo.workxplorer.uz",
    ".workxplorer.uz",
    "localhost",
    "127.0.0.1",
]

# Remove development-only apps (debug_toolbar is never installed in the demo image)
_dev_apps = set(DEVELOPMENT_APPS) | {"debug_toolbar"}
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in _dev_apps]

# Remove debug toolbar middleware
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]

# Add whitenoise middleware for demo (same as production)
try:
    import whitenoise
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    # Static files configuration for demo with whitenoise
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
except ImportError:
    # Fallback to default static file handling
    pass

# CORS settings for demo (more permissive than production for testing)
CORS_ALLOWED_ORIGINS = [
    "https://demo.workxplorer.uz",
    "https://api-demo.workxplorer.uz",
    "http://localhost:3000",  # For local frontend testing
    "http://localhost:3001",
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

# Security settings for demo (same as production)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True  # True for HTTPS
CSRF_COOKIE_SECURE = True  # True for HTTPS
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "None"
SECURE_SSL_REDIRECT = True  # True for demo with HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Higher throttle limits for demo testing
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["skill_test"] = "50/hour"

# Static files configuration for demo
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Database configuration for demo
try:
    import dj_database_url

    if env_loader.get_env("DATABASE_URL"):
        DATABASES["default"] = dj_database_url.parse(
            env_loader.get_env("DATABASE_URL"),
            conn_max_age=600,
        )
except ImportError:
    # Use existing database configuration from env_loader
    pass

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
       "handlers": ["console"],
        "level": "DEBUG",
    },
}