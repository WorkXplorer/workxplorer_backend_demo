from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class ProviderTokenEncryptionNotConfigured(Exception):
    pass


def _fernet() -> Fernet:
    key = settings.AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY
    if not key:
        raise ProviderTokenEncryptionNotConfigured(
            "AUTH_PROVIDER_TOKEN_ENCRYPTION_KEY is not set — cannot store/read "
            "an Apple provider refresh token."
        )
    return Fernet(key)


def encrypt_provider_token(raw: str) -> str:
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_provider_token(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ProviderTokenEncryptionNotConfigured(
            "Stored Apple provider token could not be decrypted — key mismatch."
        ) from exc
