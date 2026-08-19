"""Mint WebSocket connection tickets for the Go chat gateway.

A ticket is the only thing the gateway learns about a user. It is a short
lived, single-purpose JWT, deliberately separate from the platform's own
access tokens:

- It is signed with ``CHAT_JWT_SECRET``, not ``JWT_SECRET_KEY``, so a leaked
  chat secret cannot mint API sessions.
- It carries ``typ: chat_ws``; the gateway rejects any other value, so an
  access token can never be replayed as a ticket.
- It lives for ``CHAT_TICKET_TTL_SECONDS`` (60s by default) and the gateway
  refuses to accept the same ``jti`` twice.

The short life and single use matter because a browser cannot set headers on
a WebSocket handshake — the ticket has to travel in the query string, where
it lands in history and proxy logs.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings

# Roles as the gateway spells them.
ROLE_CANDIDATE = "CANDIDATE"
ROLE_RECRUITER = "RECRUITER"


class TicketError(Exception):
    """Raised when a ticket cannot be issued for the given user."""


def role_for_user(user) -> str:
    """Map a platform user onto a chat role.

    Only candidates and recruiters take part in conversations. University
    accounts and staff have no chat presence, and asking for a ticket for one
    is a programming error rather than a permission problem.
    """
    if getattr(user, "is_candidate", False):
        return ROLE_CANDIDATE
    if getattr(user, "is_recruiter", False):
        return ROLE_RECRUITER
    raise TicketError("Chat is available to candidates and recruiters only")


def issue_ticket(user) -> dict:
    """Return a freshly minted ticket for *user*.

    The response carries the ticket, its lifetime and the URL to connect to,
    so the client needs no build-time knowledge of where the gateway lives.
    """
    role = role_for_user(user)

    now = datetime.now(timezone.utc)
    ttl = int(settings.CHAT_TICKET_TTL_SECONDS)
    expires_at = now + timedelta(seconds=ttl)

    payload = {
        "sub": str(user.id),
        "role": role,
        "typ": settings.CHAT_TICKET_TYPE,
        "iss": settings.CHAT_TICKET_ISSUER,
        "aud": settings.CHAT_TICKET_AUDIENCE,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    token = jwt.encode(payload, settings.CHAT_JWT_SECRET, algorithm="HS256")
    # PyJWT returns str on 2.x; guard anyway so a 1.x pin cannot leak bytes
    # into the JSON response.
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return {
        "ticket": token,
        "expires_in": ttl,
        "expires_at": expires_at.isoformat(),
        "ws_url": settings.CHAT_WS_URL,
        "user_id": str(user.id),
        "role": role,
    }
