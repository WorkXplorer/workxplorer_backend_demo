"""Push chat events to the Go gateway (WORKXPLORER-CHAT).

The gateway holds the WebSocket connections; this module is how the platform
reaches the clients on the other end of them.

Two rules run through everything here:

1. **Nothing in this module may break a request.** Every message is committed
   to the database before it is published, so a failed push costs the
   recipient a refresh, not a message. Errors are logged and swallowed.
2. **Publishing happens after the transaction commits.** Pushing from inside
   an open transaction risks announcing a message that a later rollback
   erases, leaving a phantom bubble no reload can explain.
"""

import logging

import django_rq
import requests
from django.conf import settings
from django.db import transaction
from django.utils import translation

logger = logging.getLogger(__name__)

# Frame types, mirroring WORKXPLORER-CHAT/internal/protocol.
EVENT_MESSAGE_NEW = "message.new"
EVENT_CONVERSATION_READ = "conversation.read"

# A module-level session reuses connections to the gateway instead of paying
# for a new TCP handshake on every status change.
_session = requests.Session()


def is_enabled() -> bool:
    """Return whether realtime delivery is configured and switched on."""
    return bool(
        getattr(settings, "CHAT_ENABLED", False)
        and getattr(settings, "CHAT_INTERNAL_URL", "")
        and getattr(settings, "CHAT_SERVICE_KEY", "")
    )


def publish(user_ids, event: dict) -> bool:
    """Deliver *event* to every connected socket of *user_ids*.

    Returns True when the gateway accepted the request. Never raises.
    """
    if not is_enabled():
        return False

    recipients = [str(user_id) for user_id in user_ids if user_id]
    if not recipients:
        return False

    url = settings.CHAT_INTERNAL_URL.rstrip("/") + "/internal/publish"
    try:
        response = _session.post(
            url,
            json={"user_ids": recipients, "event": event},
            headers={"X-Chat-Service-Key": settings.CHAT_SERVICE_KEY},
            timeout=settings.CHAT_PUBLISH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # The gateway being down is an availability problem, not a data
        # problem: the row is committed and the client will fetch it.
        logger.warning(
            "Chat gateway unreachable while publishing %s to %d user(s): %s",
            event.get("type"), len(recipients), exc,
        )
        return False

    if response.status_code >= 300:
        logger.warning(
            "Chat gateway rejected %s (status %s): %s",
            event.get("type"), response.status_code, response.text[:200],
        )
        return False

    return True


def publish_on_commit(user_ids, event: dict) -> None:
    """Hand *event* to the queue once the current transaction commits.

    Two things are deliberate here.

    The commit hook is what keeps the socket honest: publishing from inside an
    open transaction risks announcing a message that a later rollback erases.

    The enqueue is what keeps the request fast. The actual HTTP call to the
    gateway runs on an RQ worker, so a slow or unreachable gateway costs a
    background job rather than the web worker handling this request. That
    matters because the gateway calls back into this platform to persist
    messages — publishing inline lets the two services block on each other,
    and on a small sync worker pool that is enough to stall the whole site.
    """
    recipients = [str(user_id) for user_id in user_ids if user_id]
    if not recipients:
        return

    def enqueue():
        from apps.conversations.tasks import deliver_event

        try:
            django_rq.get_queue("high").enqueue(
                deliver_event,
                recipients,
                event,
                # Well above the gateway timeout, so a job is killed only if
                # something is genuinely wedged rather than merely slow.
                job_timeout=30,
            )
        except Exception:
            # Redis being unavailable must not break the request that just
            # wrote the message. Realtime goes quiet; the REST endpoints still
            # return the message on the next fetch.
            logger.warning(
                "Could not queue chat event %s for %d recipient(s); "
                "it will appear on their next fetch",
                event.get("type"), len(recipients), exc_info=True,
            )

    transaction.on_commit(enqueue)


def disconnect_users(user_ids, reason: str = "session_revoked") -> bool:
    """Force-close the sockets of *user_ids*.

    Called when a session stops being valid — logout, ban, account deletion —
    so a revoked user cannot keep reading a live conversation until their
    socket happens to drop.
    """
    if not is_enabled():
        return False

    recipients = [str(user_id) for user_id in user_ids if user_id]
    if not recipients:
        return False

    url = settings.CHAT_INTERNAL_URL.rstrip("/") + "/internal/disconnect"
    try:
        response = _session.post(
            url,
            json={"user_ids": recipients, "reason": reason},
            headers={"X-Chat-Service-Key": settings.CHAT_SERVICE_KEY},
            timeout=settings.CHAT_PUBLISH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to close chat sessions for %d user(s): %s", len(recipients), exc)
        return False

    return True


def broadcast_message(message, conversation=None) -> None:
    """Push a persisted ``Message`` to both participants of its conversation.

    This is the single entry point for every server-generated message —
    status changes, uploaded documents, headhunting invitations — so a new
    message type becomes realtime by calling this once.

    Each participant is served in their own language: a status change reads
    "Ko'rib chiqilmoqda" for one side and "На рассмотрении" for the other,
    exactly as the REST endpoint would render it for each of them.
    """
    if not is_enabled():
        return

    # Everything here is guarded, not just the network call. Callers treat
    # this as fire-and-forget after their own write has succeeded — the
    # headhunting endpoint, for instance, invites a batch of candidates and
    # then broadcasts. Letting a serialization error escape would fail that
    # request after the invitations were already sent, and the recruiter
    # would reasonably try again.
    try:
        conversation = conversation or message.conversation
        participants = _participants(conversation)
        if not participants:
            return

        for user_id, language in participants:
            payload = serialize_message(message, language=language)
            publish_on_commit(
                [user_id],
                {
                    "type": EVENT_MESSAGE_NEW,
                    "data": {
                        "conversation_id": str(conversation.id),
                        "message": payload,
                    },
                },
            )
    except Exception:
        logger.error(
            "Failed to broadcast message %s; it is committed and will appear "
            "on the recipient's next fetch",
            getattr(message, "id", "<unknown>"),
            exc_info=True,
        )


def serialize_message(message, language: str | None = None) -> dict:
    """Serialize *message* exactly as the REST endpoints do.

    Reusing ``MessageSerializer`` keeps one shape for a message whether it
    arrived over the socket or in a page load, so the client never needs two
    code paths to render the same row.
    """
    from apps.conversations.serializers.conversations import MessageSerializer

    if language:
        with translation.override(language):
            return MessageSerializer(message).data
    return MessageSerializer(message).data


def _participants(conversation):
    """Return ``[(user_id, language), …]`` for a conversation.

    Falls back to the platform default language for a participant who never
    picked one.
    """
    from utils.language import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

    def normalize(value):
        if not value:
            return DEFAULT_LANGUAGE
        code = str(value).split("-")[0].lower()
        return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    participants = []
    for user in (conversation.candidate, conversation.recruiter):
        if user is None:
            continue
        participants.append((str(user.id), normalize(getattr(user, "preferred_language", None))))
    return participants
