"""How many messages a candidate may send, and when.

Recruiters answer many people and are not limited here. Candidates are, for
one reason: a recruiter's inbox is the scarce resource on this platform, and a
candidate who sends twenty messages before the recruiter has read the first
one is not communicating, they are queue-jumping.

The rule is deliberately shaped so that a real conversation never hits it:

- Up to ``CHAT_CANDIDATE_HOURLY_MESSAGE_LIMIT`` messages per conversation per
  hour, counting only messages sent **since the recruiter last wrote**. A
  reply therefore clears the quota immediately, and a genuine back-and-forth
  can run all day.
- A daily total per candidate across every conversation, high enough that
  only mass-messaging reaches it.

Both windows are rolling, so there is no midnight cliff where a blocked user
suddenly gets a fresh allowance.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.utils import timezone


# Codes returned to the client. They are distinct from the generic rate-limit
# code because they are not retryable in the same way: retrying in a second
# will fail again, and the interface must say so instead of offering a retry.
CODE_HOURLY_LIMIT = "HOURLY_LIMIT_REACHED"
CODE_DAILY_LIMIT = "DAILY_LIMIT_REACHED"


@dataclass(frozen=True)
class QuotaStatus:
    """Where a candidate stands against the per-conversation hourly quota."""

    limit: int
    used: int
    #: When the oldest message in the current window ages out, i.e. when at
    #: least one more message becomes available. None when nothing is used.
    resets_at: object | None

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0

    def as_dict(self) -> dict:
        return {
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "resets_at": self.resets_at.isoformat() if self.resets_at else None,
        }


class QuotaExceeded(Exception):
    """Raised when a candidate has no allowance left."""

    def __init__(self, code: str, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


def _hourly_limit() -> int:
    return int(getattr(settings, "CHAT_CANDIDATE_HOURLY_MESSAGE_LIMIT", 5))


def _daily_limit() -> int:
    return int(getattr(settings, "CHAT_CANDIDATE_DAILY_MESSAGE_LIMIT", 1000))


def _window_start(conversation, now):
    """Beginning of the hourly window for *conversation*.

    The window starts one hour ago, or at the recruiter's most recent message
    if that is more recent — which is what makes a reply reset the quota.

    Any message not written by the candidate counts as the other side
    engaging, including a status change with no note (those are stored as
    SYSTEM). That is deliberately generous: the cost of resetting one quota
    too eagerly is far lower than blocking someone who was invited to reply.
    """
    hour_ago = now - timedelta(hours=1)

    last_other = (
        conversation.messages
        .filter(~Q(sender_type="CANDIDATE"))
        .aggregate(latest=Max("created_at"))["latest"]
    )

    if last_other and last_other > hour_ago:
        return last_other
    return hour_ago


def hourly_status(conversation, now=None) -> QuotaStatus:
    """Return the candidate's standing in *conversation* without consuming it.

    Used by the API so the interface can show "3 of 5 left" before the
    candidate starts typing, rather than only telling them once they are
    blocked.
    """
    now = now or timezone.now()
    limit = _hourly_limit()
    start = _window_start(conversation, now)

    sent = list(
        conversation.messages
        .filter(sender_type="CANDIDATE", created_at__gt=start)
        .order_by("created_at")
        .values_list("created_at", flat=True)
    )

    resets_at = None
    if sent:
        # The window is rolling, so the next allowance appears one hour after
        # the oldest message still inside it.
        resets_at = sent[0] + timedelta(hours=1)

    return QuotaStatus(limit=limit, used=len(sent), resets_at=resets_at)


def check_candidate_can_send(conversation, candidate_id, now=None) -> QuotaStatus:
    """Raise ``QuotaExceeded`` if the candidate may not send right now.

    Returns the pre-send status when allowed, so callers can report what is
    left without querying twice.
    """
    from apps.conversations.models import Message

    now = now or timezone.now()

    status = hourly_status(conversation, now=now)
    if status.is_exhausted:
        retry_after = None
        if status.resets_at:
            retry_after = max(int((status.resets_at - now).total_seconds()), 1)
        raise QuotaExceeded(
            code=CODE_HOURLY_LIMIT,
            message=(
                f"You can send {status.limit} messages per hour in a conversation. "
                "You will be able to write again once the recruiter replies."
            ),
            retry_after_seconds=retry_after,
        )

    # Daily backstop, across every conversation this candidate takes part in.
    # Scoped by sender_type so a recruiter's messages in the same threads are
    # never counted against the candidate.
    daily_limit = _daily_limit()
    sent_today = Message.objects.filter(
        conversation__candidate_id=candidate_id,
        sender_type="CANDIDATE",
        created_at__gt=now - timedelta(days=1),
    ).count()

    if sent_today >= daily_limit:
        raise QuotaExceeded(
            code=CODE_DAILY_LIMIT,
            message=f"You have reached the daily limit of {daily_limit} messages.",
            retry_after_seconds=None,
        )

    return status
