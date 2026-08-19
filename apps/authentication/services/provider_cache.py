"""
Best-effort Redis cache shared by the social-provider clients.

Provider key material (Apple's JWKS, Google's certs) is fetched over the
network on the critical path of a login, so it gets cached — but a cache
that is down must never fail a login, so every operation here swallows its
errors and reports a miss.
"""

import logging

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_CACHE_ERRORS = (RedisError, ValueError, OSError)


def get_redis() -> Redis:
    return Redis.from_url(getattr(settings, "REDIS_URL", "redis://localhost:6380/0"))


def cache_get(key: str):
    try:
        return get_redis().get(key)
    except _CACHE_ERRORS as exc:
        logger.warning("Provider cache: failed to read %s: %s", key, exc)
        return None


def cache_set(key: str, ttl_seconds: int, value) -> None:
    try:
        get_redis().setex(key, ttl_seconds, value)
    except _CACHE_ERRORS as exc:
        logger.warning("Provider cache: failed to write %s: %s", key, exc)


def cache_delete(key: str) -> None:
    try:
        get_redis().delete(key)
    except _CACHE_ERRORS as exc:
        logger.warning("Provider cache: failed to drop %s: %s", key, exc)
