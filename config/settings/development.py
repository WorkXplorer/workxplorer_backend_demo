from config.settings.components.apps import _env_bool

from .base import *
from .env_loader import env_loader

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env_loader.get_env("SECRET_KEY", required=True)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    # "localhost",
    # "127.0.0.1",
    # "workxplorer.local",
    "*"
]

# Add development apps
INSTALLED_APPS += DEVELOPMENT_APPS

# Add debug toolbar middleware for development
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

# CORS settings for development
CORS_ALLOW_ALL_ORIGINS = True

# CSRF settings for development
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = False  # False for development (HTTP)
CSRF_COOKIE_SAMESITE = "Lax"  # More permissive for development
CLAMAV_SCAN_ENABLED = _env_bool("CLAMAV_SCAN_ENABLED", "false")

# Debug Toolbar settings
INTERNAL_IPS = [
    "127.0.0.1",
]

# Development logging
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
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "drf_spectacular": {
            "handlers": ["console"],
            "level": "CRITICAL",
            "propagate": False,
        },
    },
}
