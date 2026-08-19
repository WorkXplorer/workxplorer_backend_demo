from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.authentication.services.phone_otp_service import (
    OtpCooldownError,
    OtpDailyLimitError,
    OtpDeliveryError,
    OtpMaxAttemptsError,
    PhoneOtpService,
)


class FakeRedis:
    """Minimal in-memory stand-in for the subset of redis-py used by
    PhoneOtpService (no TTL enforcement needed — tests don't wait it out)."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        value = self.store.get(key)
        return value.encode("utf-8") if isinstance(value, str) else value

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key, ttl):
        return True

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def setex(self, key, ttl, value):
        self.ops.append(("setex", key, ttl, value))
        return self

    def delete(self, key):
        self.ops.append(("delete", key))
        return self

    def incr(self, key):
        self.ops.append(("incr", key))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        for op in self.ops:
            name = op[0]
            getattr(self.redis, name)(*op[1:])


@override_settings(
    OTP_LENGTH=6,
    OTP_TTL_SECONDS=300,
    OTP_RESEND_COOLDOWN_SECONDS=60,
    OTP_MAX_SENDS_PER_DAY=5,
    OTP_MAX_VERIFY_ATTEMPTS=5,
    OTP_SMS_TEMPLATES={"uz": "{code} test-code", "ru": "{code} test-code", "en": "{code} test-code"},
    OTP_SMS_DEFAULT_LANGUAGE="uz",
)
class PhoneOtpServiceTests(TestCase):
    def setUp(self):
        self.fake_redis = FakeRedis()
        patcher = patch.object(
            PhoneOtpService, "_get_redis_connection", return_value=self.fake_redis
        )
        self.addCleanup(patcher.stop)
        patcher.start()

        eskiz_patcher = patch(
            "apps.authentication.services.phone_otp_service.EskizClient.send_sms"
        )
        self.mock_send_sms = eskiz_patcher.start()
        self.addCleanup(eskiz_patcher.stop)

    def test_send_stores_code_and_calls_eskiz(self):
        PhoneOtpService.send("+998901234567")

        self.mock_send_sms.assert_called_once()
        stored = self.fake_redis.store["phone_otp:code:+998901234567"]
        self.assertEqual(len(stored), 6)
        self.assertTrue(stored.isdigit())

    @override_settings(
        OTP_SMS_TEMPLATES={
            "uz": "{code} uz-template",
            "ru": "{code} ru-template",
            "en": "{code} en-template",
        },
        OTP_SMS_DEFAULT_LANGUAGE="uz",
    )
    def test_send_uses_requested_language_template(self):
        PhoneOtpService.send("+998901234567", language="ru")
        message = self.mock_send_sms.call_args[0][1]
        code = self.fake_redis.store["phone_otp:code:+998901234567"]
        self.assertEqual(message, f"{code} ru-template")

    @override_settings(
        OTP_SMS_TEMPLATES={
            "uz": "{code} uz-template",
            "ru": "{code} ru-template",
            "en": "{code} en-template",
        },
        OTP_SMS_DEFAULT_LANGUAGE="uz",
    )
    def test_send_falls_back_to_default_language(self):
        # Unsupported/None language -> default (uz)
        PhoneOtpService.send("+998901234567", language=None)
        message = self.mock_send_sms.call_args[0][1]
        code = self.fake_redis.store["phone_otp:code:+998901234567"]
        self.assertEqual(message, f"{code} uz-template")

    def test_send_respects_cooldown(self):
        PhoneOtpService.send("+998901234567")
        with self.assertRaises(OtpCooldownError):
            PhoneOtpService.send("+998901234567")
        self.assertEqual(self.mock_send_sms.call_count, 1)

    def test_send_respects_daily_limit(self):
        for i in range(5):
            # bypass cooldown between sends for this test
            self.fake_redis.store.pop("phone_otp:cooldown:+998901234567", None)
            PhoneOtpService.send("+998901234567")

        self.fake_redis.store.pop("phone_otp:cooldown:+998901234567", None)
        with self.assertRaises(OtpDailyLimitError):
            PhoneOtpService.send("+998901234567")
        self.assertEqual(self.mock_send_sms.call_count, 5)

    def test_send_raises_delivery_error_when_eskiz_fails(self):
        from apps.authentication.services.eskiz_client import EskizSendError

        self.mock_send_sms.side_effect = EskizSendError("boom")
        with self.assertRaises(OtpDeliveryError):
            PhoneOtpService.send("+998901234567")

    @override_settings(OTP_SMS_TEMPLATES={"uz": None, "ru": None, "en": None})
    def test_send_fails_closed_when_no_template_configured(self):
        with self.assertRaises(OtpDeliveryError):
            PhoneOtpService.send("+998901234567")
        self.mock_send_sms.assert_not_called()

    def test_verify_correct_code_succeeds_and_clears_state(self):
        PhoneOtpService.send("+998901234567")
        code = self.fake_redis.store["phone_otp:code:+998901234567"]

        self.assertTrue(PhoneOtpService.verify("+998901234567", code))
        self.assertNotIn("phone_otp:code:+998901234567", self.fake_redis.store)

    def test_verify_wrong_code_fails_and_counts_attempt(self):
        PhoneOtpService.send("+998901234567")

        self.assertFalse(PhoneOtpService.verify("+998901234567", "000000"))
        self.assertEqual(self.fake_redis.store["phone_otp:attempts:+998901234567"], 1)

    def test_verify_locks_out_after_max_attempts(self):
        PhoneOtpService.send("+998901234567")

        for _ in range(5):
            PhoneOtpService.verify("+998901234567", "000000")

        with self.assertRaises(OtpMaxAttemptsError):
            PhoneOtpService.verify("+998901234567", "000000")
