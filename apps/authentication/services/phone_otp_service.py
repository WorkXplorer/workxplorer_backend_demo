import logging
import secrets

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

from apps.authentication.services.eskiz_client import EskizClient, EskizSendError

logger = logging.getLogger(__name__)


class OtpCooldownError(Exception):
    """Raised when a resend is requested before OTP_RESEND_COOLDOWN_SECONDS has passed."""


class OtpDailyLimitError(Exception):
    """Raised when a phone number has already hit OTP_MAX_SENDS_PER_DAY."""


class OtpDeliveryError(Exception):
    """Raised when the SMS gateway failed to deliver the code."""


class OtpMaxAttemptsError(Exception):
    """Raised when a phone number has exhausted OTP_MAX_VERIFY_ATTEMPTS for its current code."""


class PhoneOtpService:
    """
    Redis-backed phone OTP issuance/verification, same raw-connection
    pattern as LanguageCacheService. Bounds SMS cost and brute-force risk
    via a resend cooldown, a daily send cap, and a per-code verify-attempt cap.
    """

    CODE_KEY_PREFIX = "phone_otp:code"
    COOLDOWN_KEY_PREFIX = "phone_otp:cooldown"
    DAILY_COUNT_KEY_PREFIX = "phone_otp:daily"
    ATTEMPTS_KEY_PREFIX = "phone_otp:attempts"
    DAILY_TTL_SECONDS = 24 * 60 * 60

    @classmethod
    def _get_redis_connection(cls) -> Redis:
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6380/0")
        return Redis.from_url(redis_url)

    @classmethod
    def _generate_code(cls) -> str:
        length = settings.OTP_LENGTH
        return "".join(secrets.choice("0123456789") for _ in range(length))

    @classmethod
    def _resolve_template(cls, language: str = None) -> str:
        """Template for the language, falling back to the default language.
        None if neither is configured (all templates come from env)."""
        templates = settings.OTP_SMS_TEMPLATES
        return templates.get(language) or templates.get(settings.OTP_SMS_DEFAULT_LANGUAGE)

    @classmethod
    def send(cls, phone: str, language: str = None) -> None:
        """
        Generates a code, sends it via Eskiz in the given language (falling
        back to the default), and stores it for verification. Raises
        OtpCooldownError / OtpDailyLimitError / OtpDeliveryError instead of
        silently failing so the view can report back to the client.
        """
        redis_conn = cls._get_redis_connection()

        try:
            if redis_conn.get(f"{cls.COOLDOWN_KEY_PREFIX}:{phone}"):
                raise OtpCooldownError(
                    f"Please wait before requesting another code for {phone}."
                )

            daily_key = f"{cls.DAILY_COUNT_KEY_PREFIX}:{phone}"
            daily_count = int(redis_conn.get(daily_key) or 0)
            if daily_count >= settings.OTP_MAX_SENDS_PER_DAY:
                raise OtpDailyLimitError(
                    f"Daily OTP limit reached for {phone}."
                )
        except RedisError as e:
            logger.error("PhoneOtpService: Redis error checking limits for %s: %s", phone, e)
            raise

        template = cls._resolve_template(language)
        if not template:
            # No OTP_SMS_TEMPLATE_* configured for this language or the
            # default — fail closed rather than crash on None.format().
            logger.error(
                "PhoneOtpService: no OTP SMS template configured (language=%s, default=%s)",
                language, settings.OTP_SMS_DEFAULT_LANGUAGE,
            )
            raise OtpDeliveryError("No OTP SMS template configured.")

        code = cls._generate_code()

        try:
            EskizClient.send_sms(phone, template.format(code=code))
        except EskizSendError as e:
            logger.error("PhoneOtpService: failed to deliver OTP to %s: %s", phone, e)
            raise OtpDeliveryError(str(e)) from e

        try:
            pipe = redis_conn.pipeline()
            pipe.setex(f"{cls.CODE_KEY_PREFIX}:{phone}", settings.OTP_TTL_SECONDS, code)
            pipe.delete(f"{cls.ATTEMPTS_KEY_PREFIX}:{phone}")
            pipe.setex(f"{cls.COOLDOWN_KEY_PREFIX}:{phone}", settings.OTP_RESEND_COOLDOWN_SECONDS, "1")
            pipe.incr(daily_key)
            pipe.expire(daily_key, cls.DAILY_TTL_SECONDS)
            pipe.execute()
        except RedisError as e:
            # SMS already sent at this point — log but don't tell the user it
            # failed, since a code is genuinely on its way.
            logger.error("PhoneOtpService: Redis error storing OTP state for %s: %s", phone, e)

    @classmethod
    def verify(cls, phone: str, code: str) -> bool:
        """
        Returns True and clears state on a correct code. Returns False on a
        wrong code (attempts are counted). Raises OtpMaxAttemptsError once the
        attempt cap is hit, forcing a fresh /send-otp/ call.
        """
        redis_conn = cls._get_redis_connection()
        attempts_key = f"{cls.ATTEMPTS_KEY_PREFIX}:{phone}"
        code_key = f"{cls.CODE_KEY_PREFIX}:{phone}"

        try:
            attempts = int(redis_conn.get(attempts_key) or 0)
            if attempts >= settings.OTP_MAX_VERIFY_ATTEMPTS:
                raise OtpMaxAttemptsError(f"Too many attempts for {phone}.")

            stored_code = redis_conn.get(code_key)
        except RedisError as e:
            logger.error("PhoneOtpService: Redis error verifying OTP for %s: %s", phone, e)
            raise

        if not stored_code or stored_code.decode("utf-8") != code:
            try:
                pipe = redis_conn.pipeline()
                pipe.incr(attempts_key)
                pipe.expire(attempts_key, settings.OTP_TTL_SECONDS)
                pipe.execute()
            except RedisError as e:
                logger.error("PhoneOtpService: Redis error recording failed attempt for %s: %s", phone, e)
            return False

        try:
            redis_conn.delete(code_key, attempts_key)
        except RedisError as e:
            logger.error("PhoneOtpService: Redis error clearing OTP state for %s: %s", phone, e)

        return True
