from ..env_loader import env_loader

DATABASE_OPTIONS = {
    "client_encoding": "UTF8",
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_loader.get_env("DB_NAME", required=True),
        "USER": env_loader.get_env("DB_USER", required=True),
        "PASSWORD": env_loader.get_env("DB_PASSWORD", required=True),
        "HOST": env_loader.get_env("DB_HOST", "localhost"),
        "PORT": env_loader.get_env("DB_PORT", "5432"),
        "OPTIONS": DATABASE_OPTIONS,
        "CONN_MAX_AGE": 60,
    }
}
