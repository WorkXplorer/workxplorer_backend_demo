import logging

import firebase_admin
from firebase_admin import credentials
from .env_loader import env_loader

logger = logging.getLogger(__name__)


def get_firebase_credentials() -> dict:
    """Get Firebase credentials from environment variables"""
    return {
        "type": "service_account",
        "project_id": env_loader.get_env("FIREBASE_PROJECT_ID", required=True),
        "private_key_id": env_loader.get_env("FIREBASE_PRIVATE_KEY_ID", required=True),
        "private_key": env_loader.get_env(
            "FIREBASE_PRIVATE_KEY", required=True
        ).replace("\\n", "\n"),
        "client_email": env_loader.get_env("FIREBASE_CLIENT_EMAIL", required=True),
        "client_id": env_loader.get_env("FIREBASE_CLIENT_ID", required=True),
        "auth_uri": env_loader.get_env(
            "FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"
        ),
        "token_uri": env_loader.get_env(
            "FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"
        ),
        "auth_provider_x509_cert_url": env_loader.get_env(
            "FIREBASE_AUTH_PROVIDER_X509_CERT_URL"
        ),
        "client_x509_cert_url": env_loader.get_env("FIREBASE_CLIENT_X509_CERT_URL"),
        "universe_domain": env_loader.get_env(
            "FIREBASE_UNIVERSE_DOMAIN", "googleapis.com"
        ),
    }


def initialize_firebase():
    """Initialize Firebase app if not already initialized"""
    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            cred = credentials.Certificate(get_firebase_credentials())
            firebase_admin.initialize_app(cred)
        except Exception as e:
            logger.warning("Firebase initialization failed: %s", e)


# FCM Settings
FCM_DJANGO_SETTINGS = {
    "VAPID_KEY": env_loader.get_env("FIREBASE_VAPID_KEY"),
    "DEFAULT_FIREBASE_APP": None,
    "APP_VERBOSE_NAME": "WorkXplorer FCM",
    "ONE_DEVICE_PER_USER": True,
    "DELETE_INACTIVE_DEVICES": True,
}
