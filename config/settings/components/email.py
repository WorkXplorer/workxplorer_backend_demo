from ..env_loader import env_loader

# ===================== Google Business Email SMTP configurations =====================
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env_loader.get_env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env_loader.get_env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_loader.get_env("EMAIL_USE_TLS", "False") == "True"
EMAIL_HOST_USER = env_loader.get_env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env_loader.get_env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env_loader.get_env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

# Frontend & Site
FRONTEND_URL = env_loader.get_env("FRONTEND_URL")
SITE_NAME = env_loader.get_env("SITE_NAME", "WORKXPLORER")
