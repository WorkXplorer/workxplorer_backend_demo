from ..env_loader import env_loader

# Eskiz.uz SMS gateway — used to deliver phone-verification OTP codes.
ESKIZ_BASE_URL = env_loader.get_env("ESKIZ_BASE_URL", "https://notify.eskiz.uz/api")
ESKIZ_EMAIL = env_loader.get_env("ESKIZ_EMAIL")
ESKIZ_PASSWORD = env_loader.get_env("ESKIZ_PASSWORD")
# Sender nickname approved on the Eskiz account. "4546" is Eskiz's shared
# test sender for accounts without an approved nickname yet.
ESKIZ_SMS_SENDER = env_loader.get_env("ESKIZ_SMS_SENDER", "4546")

# OTP message text, per language, taken entirely from env — nothing hardcoded.
# The OTP is sent in the requester's language (Accept-Language), falling back
# to OTP_SMS_DEFAULT_LANGUAGE. Eskiz's shared "4546" sender only relays
# pre-approved templates, so each value MUST exactly match a template approved
# in the Eskiz dashboard and MUST contain "{code}" (Eskiz treats the digits as
# the variable part). Unset => phone OTP send fails closed (no SMS goes out).
OTP_SMS_TEMPLATES = {
    "uz": env_loader.get_env("OTP_SMS_TEMPLATE_UZ"),
    "ru": env_loader.get_env("OTP_SMS_TEMPLATE_RU"),
    "en": env_loader.get_env("OTP_SMS_TEMPLATE_EN"),
}
OTP_SMS_DEFAULT_LANGUAGE = "uz"

# Phone OTP verification tuning
OTP_LENGTH = int(env_loader.get_env("OTP_LENGTH", "6"))
OTP_TTL_SECONDS = int(env_loader.get_env("OTP_TTL_SECONDS", "300"))  # 5 minutes
OTP_RESEND_COOLDOWN_SECONDS = int(env_loader.get_env("OTP_RESEND_COOLDOWN_SECONDS", "60"))
OTP_MAX_SENDS_PER_DAY = int(env_loader.get_env("OTP_MAX_SENDS_PER_DAY", "5"))
OTP_MAX_VERIFY_ATTEMPTS = int(env_loader.get_env("OTP_MAX_VERIFY_ATTEMPTS", "5"))
