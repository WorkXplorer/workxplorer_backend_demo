import os

# Redis Cache Configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "workxplorer",
        "VERSION": 1,
        "TIMEOUT": 300,  # Default timeout: 5 minutes
    }
}

# Session cache
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# Cache timeout constants
TIMEZONE_CACHE_TIMEOUT = 60 * 60 * 24 * 365  # 1 year for timezone cache
USER_PERMISSION_CACHE_TIMEOUT = 60 * 15  # 15 minutes for permissions
AI_RESPONSE_CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours for AI resume generation responses