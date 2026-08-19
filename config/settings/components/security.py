from datetime import timedelta
from ..env_loader import env_loader

# JWT Settings
JWT_SECRET_KEY = env_loader.get_env("JWT_SECRET_KEY", required=True)

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(env_loader.get_env("ACCESS_TOKEN_LIFETIME_MINUTES", "15"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(env_loader.get_env("REFRESH_TOKEN_LIFETIME_DAYS", "1"))
    ),
    "EXTENDED_REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(env_loader.get_env("EXTENDED_REFRESH_TOKEN_LIFETIME_DAYS", "30"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(
        minutes=int(env_loader.get_env("ACCESS_TOKEN_LIFETIME_MINUTES", "15"))
    ),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(
        days=int(env_loader.get_env("REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
}

# Shared secret the React Native app sends on the X-Mobile-App-Key header to
# reach apps/authentication/views/mobile_auth.py. Not set => mobile auth
# endpoints refuse all requests (fail closed) rather than silently allowing
# any client through.
MOBILE_APP_API_KEY = env_loader.get_env("MOBILE_APP_API_KEY")

# --- Mobile session model (opaque refresh tokens, see MobileSessionService) ---
# HMAC key used to digest opaque refresh tokens before storing them — the raw
# token is never written to the DB. Falls back to JWT_SECRET_KEY only so dev
# environments work out of the box; set a distinct secret in production.
AUTH_REFRESH_PEPPER = env_loader.get_env("AUTH_REFRESH_PEPPER") or JWT_SECRET_KEY

# Idle timeout: reset to now + this many days on every successful refresh, so
# a session that keeps getting used effectively never expires.
MOBILE_SESSION_IDLE_TTL_DAYS = int(env_loader.get_env("MOBILE_SESSION_IDLE_TTL_DAYS", "60"))
# Absolute timeout: fixed from session creation, never extended — forces a
# fresh login at least this often even for a continuously-active session.
MOBILE_SESSION_ABSOLUTE_TTL_DAYS = int(env_loader.get_env("MOBILE_SESSION_ABSOLUTE_TTL_DAYS", "180"))

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
