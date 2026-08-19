"""
Redis-backed pending quiz result service.

When an anonymous user submits a quiz and their email already exists (cases 2 & 3),
we store their quiz result ID in a Redis cache keyed by email with a 1-hour TTL.
After the user authenticates (via set-password or login), we attach the pending
quiz result to their candidate account.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PATTERN = "pending_quiz:{email}"
_TTL = 3600  # 1 hour


def _key(email: str) -> str:
    return _CACHE_KEY_PATTERN.format(email=email.lower().strip())


def store_pending(email: str, quiz_result_id: str) -> None:
    """Store a pending quiz result ID for the given email."""
    cache.set(_key(email), str(quiz_result_id), timeout=_TTL)
    logger.debug("Stored pending quiz result %s for %s", quiz_result_id, email)


def get_pending(email: str) -> str | None:
    """Return the pending quiz result ID for the given email, or None."""
    return cache.get(_key(email))


def clear_pending(email: str) -> None:
    """Remove any pending quiz result entry for the given email."""
    cache.delete(_key(email))


def attach_pending_to_candidate(candidate) -> bool:
    """
    Look up a cached pending quiz result for the candidate's email, attach it,
    then clear the cache entry.

    Returns True if a result was attached, False otherwise.
    """
    # Lazy import to avoid circular dependencies at module load time.
    from apps.quiz.models import QuizResult

    quiz_result_id = get_pending(candidate.email)
    if not quiz_result_id:
        return False

    try:
        result = QuizResult.objects.filter(
            id=quiz_result_id,
            candidate__isnull=True,
        ).first()
        if result:
            result.candidate = candidate
            result.save(update_fields=["candidate"])
            logger.info(
                "Attached pending quiz result %s to candidate %s",
                quiz_result_id,
                candidate.id,
            )
            clear_pending(candidate.email)
            return True
    except Exception:
        logger.exception(
            "Failed to attach pending quiz result %s to candidate %s",
            quiz_result_id,
            getattr(candidate, "id", "?"),
        )
        clear_pending(candidate.email)

    return False
