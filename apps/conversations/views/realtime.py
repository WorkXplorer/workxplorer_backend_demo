"""The client-facing half of the chat integration: minting connection tickets."""

import logging

from django.conf import settings
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.responses import APIResponse
from apps.conversations.tickets import TicketError, issue_ticket

logger = logging.getLogger(__name__)


@extend_schema(
    request=None,
    description=_(
        "Issue a short-lived, single-use ticket for opening a chat WebSocket. "
        "Connect to the returned ws_url with the ticket in the `ticket` query "
        "parameter. Tickets expire in seconds and cannot be reused — fetch a "
        "fresh one for every connection attempt, including reconnects."
    ),
    examples=[
        OpenApiExample(
            "Issued ticket",
            value={
                "ticket": "eyJhbGciOiJIUzI1NiIs…",
                "expires_in": 60,
                "expires_at": "2026-07-29T10:31:00+00:00",
                "ws_url": "wss://chat.workxplorer.uz/ws",
                "user_id": "0197e0c1-2f3a-7c4d-9b21-5f6a7b8c9d0e",
                "role": "CANDIDATE",
            },
            response_only=True,
        )
    ],
)
class ChatTicketView(APIView):
    """Issue a WebSocket connection ticket for the authenticated user.

    This is the only place a chat session begins. The client never holds a
    long-lived chat credential: it exchanges its ordinary API session for a
    ticket that is valid for one connection and about a minute.
    """

    permission_classes = [IsAuthenticated]
    # A client fetches a ticket per connection, and a flaky network means
    # reconnects. A dedicated bucket keeps that traffic from eating the
    # user's allowance for the rest of the API, while still capping a client
    # stuck in a reconnect loop.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat_ticket"

    def post(self, request):
        if not settings.CHAT_ENABLED:
            return APIResponse.error(
                message=_("Realtime chat is currently unavailable"),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="CHAT_DISABLED",
            )

        try:
            payload = issue_ticket(request.user)
        except TicketError as exc:
            return APIResponse.error(
                message=str(exc),
                status_code=status.HTTP_403_FORBIDDEN,
                code="CHAT_ROLE_NOT_SUPPORTED",
            )

        return APIResponse.success(data=payload, message=_("Chat ticket issued"))


chat_ticket_view = ChatTicketView.as_view()
