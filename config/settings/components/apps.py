from ..env_loader import env_loader

INSTALLED_APPS = [
    # Third party app for model translations (must come before translated apps)
    "modeltranslation",
    # Custom apps
    "apps.matching",
    "apps.applications",
    "apps.resumes",
    "apps.vacancies",
    "apps.skills",
    "apps.edupartners",
    "apps.profiles",
    "apps.authentication",
    "apps.quiz",
    "apps.notifications",
    "apps.authentication.schema",
    "apps.general",
    "apps.domain",
    "apps.subscriptions",
    "apps.conversations",
    "apps.hr_templates",
    "apps.languages",
    "apps.ai",
    "apps.banners",
    "apps.student_analytics",
    "apps.skill_tests",
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third party apps
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "fcm_django",
    "drf_spectacular",
    "django_rq",
    "import_export",
]

# Development-only apps
DEVELOPMENT_APPS = [
    "debug_toolbar",
    # "django_extensions"
]

AUTH_USER_MODEL = "authentication.CustomUser"

SITE_ID = 1

EMBEDDING_SERVICE_URL = env_loader.get_env(
    "EMBEDDING_SERVICE_URL", "http://embedding-service:8000"
)

# HeadHunter / hh.uz API integration.
# Vacancy search currently requires an application access token from dev.hh.uz
# / dev.hh.ru. Keep it optional so local development can run without HH access.
HH_API_BASE_URL = env_loader.get_env("HH_API_BASE_URL", "https://api.hh.uz")
HH_USER_AGENT = env_loader.get_env(
    "HH_USER_AGENT",
    "WorkXplorer/1.0 (https://workxplorer.uz)",
)
HH_ACCESS_TOKEN = env_loader.get_env("HH_ACCESS_TOKEN", default=None)
HH_CLIENT_ID = env_loader.get_env("HH_CLIENT_ID", default=None)
HH_CLIENT_SECRET = env_loader.get_env("HH_CLIENT_SECRET", default=None)
HH_TOKEN_URL = env_loader.get_env("HH_TOKEN_URL", "https://hh.ru/oauth/token")
HH_TOKEN_CACHE_SECONDS = env_loader.get_env("HH_TOKEN_CACHE_SECONDS", "86400")

# Uzbekistan National Statistics Committee (siat.stat.uz) official sector
# salary data, used as a sanity-check band on the HH-derived market estimate.
STAT_UZ_API_BASE_URL = env_loader.get_env("STAT_UZ_API_BASE_URL", "https://siat.stat.uz")
STAT_UZ_SALARY_DATASET_ID = env_loader.get_env("STAT_UZ_SALARY_DATASET_ID", "506")


def _env_bool(key: str, default: str = "false") -> bool:
    value = env_loader.get_env(key, default)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


# Antivirus scanning is OFF by default so unit-tests and local dev without a
# running ClamAV daemon still work.  Explicitly set CLAMAV_SCAN_ENABLED=true
# in production/docker environments (done via docker-compose).
CLAMAV_SCAN_ENABLED = _env_bool("CLAMAV_SCAN_ENABLED", "false")
CLAMAV_FAIL_OPEN = _env_bool("CLAMAV_FAIL_OPEN", "false")
CLAMAV_ENGINE = env_loader.get_env("CLAMAV_ENGINE", "clamav-client")
CLAMAV_BACKEND = env_loader.get_env("CLAMAV_BACKEND", "clamd")
CLAMAV_ADDRESS = env_loader.get_env("CLAMAV_ADDRESS", "127.0.0.1:3310")
CLAMAV_TIMEOUT = float(env_loader.get_env("CLAMAV_TIMEOUT", "3"))
CLAMAV_STREAM = _env_bool("CLAMAV_STREAM", "true")
CLAMAV_MAX_FILE_SIZE_MB = float(env_loader.get_env("CLAMAV_MAX_FILE_SIZE_MB", "2000"))
CLAMAV_MAX_SCAN_SIZE_MB = float(env_loader.get_env("CLAMAV_MAX_SCAN_SIZE_MB", "2000"))
CLAMAV_CACHE_ENABLED = _env_bool("CLAMAV_CACHE_ENABLED", "true")
CLAMAV_CACHE_TTL_SECONDS = int(env_loader.get_env("CLAMAV_CACHE_TTL_SECONDS", "3600"))
