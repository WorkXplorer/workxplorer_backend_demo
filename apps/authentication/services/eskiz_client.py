import logging

import requests
from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class EskizSendError(Exception):
    pass


class EskizClient:
    """
    Thin client for the Eskiz.uz SMS gateway (https://notify.eskiz.uz).

    Eskiz auth tokens are valid for ~30 days; we cache the token in Redis
    (same raw-connection pattern as LanguageCacheService) well under that so
    a stale token is never used for long, and transparently re-authenticate
    on a 401 from the send endpoint.
    """

    TOKEN_CACHE_KEY = "eskiz:auth_token"
    TOKEN_CACHE_TTL_SECONDS = 20 * 24 * 60 * 60  # 20 days

    @classmethod
    def _get_redis_connection(cls) -> Redis:
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6380/0")
        return Redis.from_url(redis_url)

    @classmethod
    def _login(cls) -> str:
        response = requests.post(
            f"{settings.ESKIZ_BASE_URL}/auth/login",
            data={"email": settings.ESKIZ_EMAIL, "password": settings.ESKIZ_PASSWORD},
            timeout=10,
        )
        response.raise_for_status()
        token = response.json()["data"]["token"]

        try:
            redis_conn = cls._get_redis_connection()
            redis_conn.setex(cls.TOKEN_CACHE_KEY, cls.TOKEN_CACHE_TTL_SECONDS, token)
        except RedisError as e:
            logger.warning("Eskiz: failed to cache auth token: %s", e)

        return token

    @classmethod
    def _get_token(cls, force_refresh: bool = False) -> str:
        if not force_refresh:
            try:
                redis_conn = cls._get_redis_connection()
                cached = redis_conn.get(cls.TOKEN_CACHE_KEY)
                if cached:
                    return cached.decode("utf-8")
            except RedisError as e:
                logger.warning("Eskiz: failed to read cached auth token: %s", e)

        return cls._login()

    @classmethod
    def send_sms(cls, phone: str, message: str) -> None:
        """
        Sends an SMS via Eskiz. Raises EskizSendError on failure — callers
        should treat that as "OTP not delivered" rather than pretending
        success.
        """
        # Eskiz expects the number without the leading '+'.
        mobile_phone = phone.lstrip("+")

        try:
            for attempt in (1, 2):
                token = cls._get_token(force_refresh=attempt == 2)
                response = requests.post(
                    f"{settings.ESKIZ_BASE_URL}/message/sms/send",
                    headers={"Authorization": f"Bearer {token}"},
                    data={
                        "mobile_phone": mobile_phone,
                        "message": message,
                        "from": settings.ESKIZ_SMS_SENDER,
                    },
                    timeout=10,
                )

                if response.status_code == 401 and attempt == 1:
                    continue  # token expired/invalid — force a fresh login and retry once

                if not response.ok:
                    logger.error(
                        "Eskiz SMS send failed for %s: %s %s",
                        mobile_phone, response.status_code, response.text,
                    )
                    raise EskizSendError(f"Eskiz responded {response.status_code}")

                return
        except requests.RequestException as e:
            logger.error("Eskiz SMS send request failed for %s: %s", mobile_phone, e)
            raise EskizSendError(str(e)) from e

        raise EskizSendError("Eskiz authentication failed after retry")
