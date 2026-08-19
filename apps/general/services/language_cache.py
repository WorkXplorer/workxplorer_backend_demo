import logging

from django.conf import settings
from redis import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class LanguageCacheService:
    """
    Redis-based user language preference caching service.

    Stores user language preferences in Redis for fast lookups.
    Used primarily for email language selection.
    """

    CACHE_KEY_PREFIX = "user_language"
    CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
    DEFAULT_LANGUAGE = "en"
    SUPPORTED_LANGUAGES = ("en", "ru", "uz")

    @classmethod
    def _get_redis_connection(cls) -> Redis:
        """Get Redis connection."""
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6380/0")
        return Redis.from_url(redis_url)

    @classmethod
    def _get_cache_key(cls, user_id: str) -> str:
        """Generate cache key for user."""
        return f"{cls.CACHE_KEY_PREFIX}:{user_id}"

    @classmethod
    def get_user_language(cls, user_id: str) -> str:
        """
        Get cached language preference for user.

        Args:
            user_id: User ID (UUID as string)

        Returns:
            Language code (en, ru, uz). Returns DEFAULT_LANGUAGE if not cached.
        """
        cache_key = cls._get_cache_key(user_id)

        try:
            redis_conn = cls._get_redis_connection()
            cached_value = redis_conn.get(cache_key)

            if cached_value is None:
                logger.debug(
                    f"[LANGUAGE_CACHE] No cached language for user {user_id}, "
                    f"returning default: {cls.DEFAULT_LANGUAGE}"
                )
                return cls.DEFAULT_LANGUAGE

            language = cached_value.decode("utf-8")

            if language not in cls.SUPPORTED_LANGUAGES:
                logger.warning(
                    f"[LANGUAGE_CACHE] Invalid cached language '{language}' for user {user_id}, "
                    f"returning default: {cls.DEFAULT_LANGUAGE}"
                )
                return cls.DEFAULT_LANGUAGE

            logger.debug(
                f"[LANGUAGE_CACHE] Retrieved language '{language}' for user {user_id}"
            )
            return language

        except RedisError as e:
            logger.error(
                f"[LANGUAGE_CACHE] Redis error getting language for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return cls.DEFAULT_LANGUAGE
        except Exception as e:
            logger.error(
                f"[LANGUAGE_CACHE] Unexpected error getting language for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return cls.DEFAULT_LANGUAGE

    @classmethod
    def set_user_language(cls, user_id: str, language: str) -> bool:
        """
        Set user language preference in cache.

        Args:
            user_id: User ID (UUID as string)
            language: Language code (must be in SUPPORTED_LANGUAGES)

        Returns:
            True if successful, False otherwise
        """
        if language not in cls.SUPPORTED_LANGUAGES:
            logger.warning(
                f"[LANGUAGE_CACHE] Invalid language '{language}' for user {user_id}. "
                f"Supported languages: {cls.SUPPORTED_LANGUAGES}"
            )
            return False

        cache_key = cls._get_cache_key(user_id)

        try:
            redis_conn = cls._get_redis_connection()
            redis_conn.setex(cache_key, cls.CACHE_TTL_SECONDS, language)

            logger.info(
                f"[LANGUAGE_CACHE] Set language '{language}' for user {user_id} "
                f"(TTL: {cls.CACHE_TTL_SECONDS}s)"
            )
            return True

        except RedisError as e:
            logger.error(
                f"[LANGUAGE_CACHE] Redis error setting language for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"[LANGUAGE_CACHE] Unexpected error setting language for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False

    @classmethod
    def delete_user_language(cls, user_id: str) -> bool:
        """
        Remove user language preference from cache.

        Args:
            user_id: User ID (UUID as string)

        Returns:
            True if deleted, False otherwise
        """
        cache_key = cls._get_cache_key(user_id)

        try:
            redis_conn = cls._get_redis_connection()
            deleted_count = redis_conn.delete(cache_key)

            if deleted_count > 0:
                logger.info(
                    f"[LANGUAGE_CACHE] Deleted language preference for user {user_id}"
                )
                return True
            else:
                logger.debug(
                    f"[LANGUAGE_CACHE] No language preference to delete for user {user_id}"
                )
                return False

        except RedisError as e:
            logger.error(
                f"[LANGUAGE_CACHE] Redis error deleting language for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"[LANGUAGE_CACHE] Unexpected error deleting language for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False

    @classmethod
    def refresh_ttl(cls, user_id: str) -> bool:
        """
        Refresh the TTL for a user's language preference.

        Args:
            user_id: User ID (UUID as string)

        Returns:
            True if TTL was refreshed, False if key doesn't exist
        """
        cache_key = cls._get_cache_key(user_id)

        try:
            redis_conn = cls._get_redis_connection()
            result = redis_conn.expire(cache_key, cls.CACHE_TTL_SECONDS)

            if result:
                logger.debug(
                    f"[LANGUAGE_CACHE] Refreshed TTL for user {user_id} "
                    f"(TTL: {cls.CACHE_TTL_SECONDS}s)"
                )
                return True
            else:
                logger.debug(
                    f"[LANGUAGE_CACHE] Cannot refresh TTL for user {user_id}: "
                    "key does not exist"
                )
                return False

        except RedisError as e:
            logger.error(
                f"[LANGUAGE_CACHE] Redis error refreshing TTL for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"[LANGUAGE_CACHE] Unexpected error refreshing TTL for user {user_id}: "
                f"{type(e).__name__}: {e}"
            )
            return False
