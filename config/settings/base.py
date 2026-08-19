from pathlib import Path
from .components import *
from .firebase import initialize_firebase

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize Firebase
initialize_firebase()

# Core Django Settings
ROOT_URLCONF = "config.urls.base"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TEST_RUNNER = "core.test_runner.WorkXplorerTestRunner"

# Disable APPEND_SLASH to prevent 301 redirects that change
# HTTP methods (e.g., DELETE → GET) for API endpoints.
# APPEND_SLASH = False
IMPORT_EXPORT_TMP_STORAGE_CLASS = "import_export.tmp_storages.MediaStorage"

# File Upload Settings
# Maximum size in bytes for request body (10MB default, increased to 50MB for file uploads)
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB
# Maximum size for uploaded files (50MB)
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50MB

# Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom middleware (order matters)
    "utils.middleware.request_logging.RequestLoggingMiddleware",  # Log requests
    "utils.middleware.input_validation.InputValidationMiddleware",  # Validate input
    "utils.middleware.error_handling.GlobalErrorHandlingMiddleware",  # Handle errors
    # Account middleware (after auth middleware)
    "allauth.account.middleware.AccountMiddleware",
]

SILENCED_SYSTEM_CHECKS = ["allauth.E001"]
