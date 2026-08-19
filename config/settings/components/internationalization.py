from pathlib import Path
from ..env_loader import env_loader

# Get BASE_DIR from the path resolution
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Internationalization
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("uz", "Uzbek"),
    ("en", "English"),
    ("ru", "Russian"),
]

LOCALE_PATHS = [
    str(BASE_DIR / "locale"),
]

MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
MODELTRANSLATION_LANGUAGES = ("uz", "en", "ru")

EDUPARTNER_SERVICE_KEY = env_loader.get_env("EDUPARTNER_SERVICE_KEY", default="")

# Webhook URLs for analytics services
HR_ANALYTICS_COMPANY_WEBHOOK_URL = env_loader.get_env("HR_ANALYTICS_COMPANY_WEBHOOK_URL", "")
HR_ANALYTICS_VACANCY_WEBHOOK_URL = env_loader.get_env("HR_ANALYTICS_VACANCY_WEBHOOK_URL", "")
EDUPARTNER_ANALYTICS_WEBHOOK_URL = env_loader.get_env("EDUPARTNER_ANALYTICS_WEBHOOK_URL", "")

# Vault Service (LMS Grade Sync)
VAULT_SERVICE_URL = env_loader.get_env("VAULT_SERVICE_URL", "http://localhost:8004")
VAULT_TOKEN = env_loader.get_env("VAULT_TOKEN", "")

# Telegram Bot for partner notifications
TELEGRAM_BOT_API_URL = env_loader.get_env("TELEGRAM_BOT_API_URL", "http://workxplorer-bot:5000")
TELEGRAM_BOT_API_SECRET = env_loader.get_env("TELEGRAM_BOT_API_SECRET", "")

# Backend API URL for internal use (e.g., admin actions)
BACKEND_API_URL = env_loader.get_env("BACKEND_API_URL", "http://localhost:8000")

# Cooldown period in minutes for counting vacancy views
VACANCY_VIEW_COOLDOWN_MINUTES = env_loader.get_env("VACANCY_VIEW_COOLDOWN_MINUTES", 60)