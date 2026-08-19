"""Endpoints the Go chat gateway calls on behalf of a connected user.

The gateway holds sockets and knows nothing else. Every decision that needs
the database — may this user write here, who should receive this, what does
the persisted row look like — is made here.

Two constraints shape every view in this module:

- **The caller is a service, not a user.** ``IsChatService`` authenticates the
  gateway by shared secret; the acting user arrives as a ``user_id`` in the
  request. That id is *not* trusted to imply permission: each view re-derives
  what the user may do from the conversation itself.
- **The gateway is on the hot path of every keystroke-to-delivery.** These
  views stay narrow and indexed, and they never call back out to the gateway
  (the gateway does its own fan-out from the response).
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.responses import APIResponse

from apps.conversations.models import Conversation, Message, MessageType
from apps.conversations.permissions import IsChatService
from apps.conversations.quotas import QuotaExceeded, check_candidate_can_send
from apps.conversations.realtime import serialize_message
from apps.conversations.tickets import ROLE_CANDIDATE, ROLE_RECRUITER
from utils.html_sanitizer import validate_safe_html

logger = logging.getLogger(__name__)


class InternalChatView(APIView):
    """Base class for gateway-facing endpoints.

    Authentication and throttling are both cleared deliberately:

    - The platform's default authentication reads user cookies, which a
      service call does not have; ``IsChatService`` replaces it entirely.
    - The default ``AnonRateThrottle`` counts by IP. Every gateway call
      arrives from one IP, so the shared 10000/day bucket would throttle all
      of chat platform-wide within a day of normal use. Per-connection rate
      limiting lives in the gateway, where it can be applied per user.
    """

    authentication_classes = []
    permission_classes = [IsChatService]
    throttle_classes = []


def _load_conversation(conversation_id, user_id, role):
    """Return the conversation *user_id* may act in, or ``None``.

    Membership is checked against the column matching the caller's role, so a
    recruiter cannot act as the candidate side of their own conversation by
    passing the candidate's id.
    """
    queryset = Conversation.objects.select_related("candidate", "recruiter")

    if role == ROLE_CANDIDATE:
        queryset = queryset.filter(candidate_id=user_id)
    elif role == ROLE_RECRUITER:
        queryset = queryset.filter(recruiter_id=user_id)
    else:
        return None

    return queryset.filter(id=conversation_id).first()


def _participants(conversation):
    """Return both participants' ids, for the gateway's fan-out."""
    return [str(conversation.candidate_id), str(conversation.recruiter_id)]


class InternalMessageCreateView(InternalChatView):
    """Persist a message a user sent over the WebSocket.

    The response tells the gateway what to broadcast and to whom. The message
    is committed before the gateway sees it, so anything the client receives
    is guaranteed to survive a reload.
    """

    def post(self, request):
        user_id = str(request.data.get("user_id") or "").strip()
        role = str(request.data.get("role") or "").strip().upper()
        conversation_id = str(request.data.get("conversation_id") or "").strip()
        content = request.data.get("content")

        if not user_id or not conversation_id:
            return _error("user_id and conversation_id are required", status.HTTP_400_BAD_REQUEST)
        if role not in (ROLE_CANDIDATE, ROLE_RECRUITER):
            return _error("role must be CANDIDATE or RECRUITER", status.HTTP_400_BAD_REQUEST)
        if not isinstance(content, str):
            return _error("content must be a string", status.HTTP_400_BAD_REQUEST)

        # Chat bubbles are rendered as HTML on the client, so message bodies
        # are sanitized here rather than at render time — this is the single
        # door user-authored chat content comes through.
        content = validate_safe_html(content).strip()
        if not content:
            return _error("content is empty", status.HTTP_400_BAD_REQUEST)

        max_length = settings.CHAT_MAX_MESSAGE_LENGTH
        if len(content) > max_length:
            return _error(
                f"content exceeds {max_length} characters",
                status.HTTP_400_BAD_REQUEST,
            )

        conversation = _load_conversation(conversation_id, user_id, role)
        if conversation is None:
            # Not distinguishing "missing" from "not yours" on purpose: the
            # gateway would otherwise be a conversation-id oracle.
            return _error("Conversation not found", status.HTTP_404_NOT_FOUND)

        # Candidates have a message budget; recruiters do not. Checked after
        # authorization so an outsider learns nothing about a conversation's
        # traffic, and before the write so a rejected message is never stored.
        if role == ROLE_CANDIDATE:
            try:
                check_candidate_can_send(conversation, user_id)
            except QuotaExceeded as exc:
                # Built through APIResponse so the body is the platform's
                # standard error envelope; a bare dict would be rewrapped by
                # StandardJSONRenderer and lose the code and retry_after.
                return APIResponse.error(
                    message=exc.message,
                    code=exc.code,
                    details={"retry_after": exc.retry_after_seconds},
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                sender_type=role,
                message_type=MessageType.TEXT,
                content=content,
                is_read=False,
            )

            # The sender has by definition read their own conversation; the
            # other side has not.
            if role == ROLE_CANDIDATE:
                conversation.is_read_by_candidate = True
                conversation.is_read_by_recruiter = False
            else:
                conversation.is_read_by_recruiter = True
                conversation.is_read_by_candidate = False
            conversation.save(
                update_fields=["is_read_by_candidate", "is_read_by_recruiter", "updated_at"]
            )

        logger.info(
            "Chat message %s persisted in conversation %s by %s",
            message.id, conversation.id, role,
        )

        return Response(
            {
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "created_at": message.created_at.isoformat(),
                "message": serialize_message(message),
                "recipients": _participants(conversation),
            },
            status=status.HTTP_201_CREATED,
        )


class InternalMarkReadView(InternalChatView):
    """Persist a read receipt sent over the WebSocket.

    Mirrors what the REST detail endpoint does when a conversation is opened,
    so a user reading in a live socket and a user reloading the page end up in
    the same state.
    """

    def post(self, request):
        user_id = str(request.data.get("user_id") or "").strip()
        role = str(request.data.get("role") or "").strip().upper()
        conversation_id = str(request.data.get("conversation_id") or "").strip()

        if not user_id or not conversation_id:
            return _error("user_id and conversation_id are required", status.HTTP_400_BAD_REQUEST)
        if role not in (ROLE_CANDIDATE, ROLE_RECRUITER):
            return _error("role must be CANDIDATE or RECRUITER", status.HTTP_400_BAD_REQUEST)

        conversation = _load_conversation(conversation_id, user_id, role)
        if conversation is None:
            return _error("Conversation not found", status.HTTP_404_NOT_FOUND)

        # Only messages from the *other* side become read — a user reading
        # their own outbox would otherwise mark the recipient's unread
        # messages as seen.
        counterpart = ROLE_RECRUITER if role == ROLE_CANDIDATE else ROLE_CANDIDATE

        with transaction.atomic():
            conversation.messages.filter(is_read=False, sender_type=counterpart).update(is_read=True)

            if role == ROLE_CANDIDATE and not conversation.is_read_by_candidate:
                conversation.is_read_by_candidate = True
                conversation.save(update_fields=["is_read_by_candidate", "updated_at"])
            elif role == ROLE_RECRUITER and not conversation.is_read_by_recruiter:
                conversation.is_read_by_recruiter = True
                conversation.save(update_fields=["is_read_by_recruiter", "updated_at"])

        return Response(
            {
                "conversation_id": str(conversation.id),
                "read_at": timezone.now().isoformat(),
                # The receipt is only interesting to the other party.
                "recipients": [
                    str(
                        conversation.recruiter_id
                        if role == ROLE_CANDIDATE
                        else conversation.candidate_id
                    )
                ],
            }
        )


class InternalMembershipView(InternalChatView):
    """Return a conversation's participants.

    The gateway uses this to route ephemeral events — typing indicators —
    that never touch the database. Because it is scoped to the asking user,
    it doubles as the permission check for those events: without it a client
    could probe conversations it has nothing to do with.
    """

    def get(self, request):
        conversation_id = str(request.query_params.get("conversation_id") or "").strip()
        user_id = str(request.query_params.get("user_id") or "").strip()

        if not conversation_id or not user_id:
            return _error("conversation_id and user_id are required", status.HTTP_400_BAD_REQUEST)

        conversation = (
            Conversation.objects
            .only("id", "candidate_id", "recruiter_id")
            .filter(id=conversation_id)
            .first()
        )
        if conversation is None:
            return _error("Conversation not found", status.HTTP_404_NOT_FOUND)

        participants = {
            str(conversation.candidate_id): ROLE_CANDIDATE,
            str(conversation.recruiter_id): ROLE_RECRUITER,
        }
        if user_id not in participants:
            return _error("Not a participant", status.HTTP_403_FORBIDDEN)

        return Response(
            {
                "conversation_id": str(conversation.id),
                "participants": [
                    {"user_id": participant_id, "role": participant_role}
                    for participant_id, participant_role in participants.items()
                ],
            }
        )


class InternalPeersView(InternalChatView):
    """Return everyone *user_id* shares a conversation with.

    Presence is announced only to these users, so a candidate coming online
    is visible to the recruiters they actually talk to and to nobody else.
    """

    def get(self, request):
        user_id = str(request.query_params.get("user_id") or "").strip()
        if not user_id:
            return _error("user_id is required", status.HTTP_400_BAD_REQUEST)

        # Both directions are covered by the (candidate, recruiter) index, and
        # values_list keeps this to two cheap index scans regardless of how
        # many conversations the user has.
        recruiter_ids = (
            Conversation.objects
            .filter(candidate_id=user_id)
            .values_list("recruiter_id", flat=True)
            .distinct()
        )
        candidate_ids = (
            Conversation.objects
            .filter(recruiter_id=user_id)
            .values_list("candidate_id", flat=True)
            .distinct()
        )

        peers = {str(peer_id) for peer_id in recruiter_ids}
        peers.update(str(peer_id) for peer_id in candidate_ids)
        peers.discard(user_id)

        return Response({"user_ids": sorted(peers)})


def _error(message, status_code):
    """Return an error the gateway can classify by status code."""
    return Response({"detail": message}, status=status_code)


internal_message_create_view = InternalMessageCreateView.as_view()
internal_mark_read_view = InternalMarkReadView.as_view()
internal_membership_view = InternalMembershipView.as_view()
internal_peers_view = InternalPeersView.as_view()
