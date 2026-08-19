from ..env_loader import env_loader


AUTHENTICATION_BACKENDS = [
    # Email or verified-phone login (superset of ModelBackend's email-only
    # lookup — also used by Django admin and anywhere else authenticate() is called)
    'apps.authentication.backends.EmailOrPhoneBackend',

    # `allauth` specific authentication methods, such as login by email
    'allauth.account.auth_backends.AuthenticationBackend',
]

APP_CLIENT_ID = env_loader.get_env("APP_CLIENT_ID")
APP_CLIENT_SECRET = env_loader.get_env("APP_CLIENT_SECRET")
APP_KEY = env_loader.get_env("APP_KEY")

# Mobile native Google Sign-In: Expo/RN is configured with this as the
# "server client ID", so the ID token it gets is audienced to it — same web
# OAuth client already used above, not a separate mobile client.
GOOGLE_SERVER_CLIENT_ID = env_loader.get_env("GOOGLE_SERVER_CLIENT_ID") or APP_CLIENT_ID

# Sign in with Apple (mobile only, iOS — see apps/authentication/services/apple_client.py)
APPLE_TEAM_ID = env_loader.get_env("APPLE_TEAM_ID")
APPLE_CLIENT_ID = env_loader.get_env("APPLE_CLIENT_ID", "com.workxplorer.app")
APPLE_KEY_ID = env_loader.get_env("APPLE_KEY_ID")
APPLE_PRIVATE_KEY = env_loader.get_env("APPLE_PRIVATE_KEY")

# Lifetime of the one-shot nonce/state issued to the mobile app before a native
# Google/Apple sign-in. It has to cover the whole native SDK detour — account
# picker, an account the user creates on the spot, 2FA, consent — so 5 minutes
# was too tight in practice on iOS. The value is still single-use and bound to
# provider + device_id, so a longer window costs very little.
OAUTH_CHALLENGE_TTL_SECONDS = int(env_loader.get_env("OAUTH_CHALLENGE_TTL_SECONDS", "900"))

# Fernet key (32 url-safe base64 bytes) encrypting the stored Apple provider
# refresh token. Generate with: Fernet.generate_key().decode()
AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY = env_loader.get_env("AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY")

# django-allauth settings
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': APP_CLIENT_ID,
            'secret': APP_CLIENT_SECRET,
            'key': APP_KEY,
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}
