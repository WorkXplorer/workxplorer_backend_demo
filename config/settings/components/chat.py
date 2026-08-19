"""Settings for the Go chat gateway (WORKXPLORER-CHAT).

The gateway holds the WebSocket connections; this platform keeps every
authorization decision and every database write. The two talk over a pair of
shared secrets:

- CHAT_JWT_SECRET signs the short-lived connection tickets the gateway
  verifies.
- CHAT_SERVICE_KEY authenticates the internal HTTP hop in both directions.

Both are deliberately distinct from JWT_SECRET_KEY: a leaked chat secret must
not be able to mint API sessions.
"""

import os

from ..env_loader import env_loader
from .security import JWT_SECRET_KEY

# Master switch. With chat disabled the REST endpoints keep working exactly
# as before — only the realtime layer goes quiet.
#
# Defaults to OFF. Enabling it in production requires the two secrets below,
# and the absence of either is a hard startup error — correct for a
# misconfigured feature, but fatal for a deployment that simply has not been
# told about chat yet. Defaulting to off means this code can ship ahead of
# the gateway and the secrets, and chat is switched on deliberately once both
# are in place.
CHAT_ENABLED = env_loader.get_env("CHAT_ENABLED", "false").lower() in ("1", "true", "yes", "on")

# Signs WebSocket connection tickets. Shared with the gateway's
# CHAT_JWT_SECRET. Falls back to JWT_SECRET_KEY so development environments
# work out of the box; production validation below refuses that fallback.
CHAT_JWT_SECRET = env_loader.get_env("CHAT_JWT_SECRET")

# Authenticates platform <-> gateway HTTP calls. Shared with the gateway's
# CHAT_SERVICE_KEY.
CHAT_SERVICE_KEY = env_loader.get_env("CHAT_SERVICE_KEY")

# How long a connection ticket is valid. Kept very short: the ticket travels
# in a query string, and the client redeems it immediately.
CHAT_TICKET_TTL_SECONDS = int(env_loader.get_env("CHAT_TICKET_TTL_SECONDS", "60"))

# The wss:// URL handed to clients along with their ticket.
CHAT_WS_URL = env_loader.get_env("CHAT_WS_URL", "ws://127.0.0.1:8080/ws")

# Root of the gateway's internal listener, used to push server-generated
# events and to force-close revoked sessions. Must not be publicly routable.
CHAT_INTERNAL_URL = env_loader.get_env("CHAT_INTERNAL_URL", "http://127.0.0.1:8081")

# Timeout for calls to the gateway. Short on purpose: these calls happen
# inside request/response cycles, and a slow gateway must never become a slow
# API. Failures are logged and swallowed — the message is already committed.
CHAT_PUBLISH_TIMEOUT_SECONDS = float(env_loader.get_env("CHAT_PUBLISH_TIMEOUT_SECONDS", "2"))

# Longest message a client may send over the socket. Mirrors the gateway's
# own limit so the two agree on what to reject.
CHAT_MAX_MESSAGE_LENGTH = int(env_loader.get_env("CHAT_MAX_MESSAGE_LENGTH", "5000"))

# --- Candidate message quotas ----------------------------------------------
# A recruiter's attention is the scarce resource here, so candidates get a
# budget and recruiters do not. See apps/conversations/quotas.py for the rule.
#
# Messages a candidate may send in one conversation per hour, counting only
# those sent since the recruiter last wrote — so a reply clears the quota and
# a real back-and-forth never hits it.
CHAT_CANDIDATE_HOURLY_MESSAGE_LIMIT = int(
    env_loader.get_env("CHAT_CANDIDATE_HOURLY_MESSAGE_LIMIT", "5")
)

# Daily total per candidate across every conversation. A backstop against
# mass-messaging, set high enough that ordinary conversation cannot reach it.
CHAT_CANDIDATE_DAILY_MESSAGE_LIMIT = int(
    env_loader.get_env("CHAT_CANDIDATE_DAILY_MESSAGE_LIMIT", "1000")
)

# Ticket claims, mirrored in the gateway's internal/auth package.
CHAT_TICKET_ISSUER = "workxplorer-platform"
CHAT_TICKET_AUDIENCE = "workxplorer-chat"
CHAT_TICKET_TYPE = "chat_ws"

# Placeholder used outside production when CHAT_SERVICE_KEY is unset. Named so
# the system check can recognise it and warn.
CHAT_DEV_SERVICE_KEY_PLACEHOLDER = "development-chat-service-key"

# Set below when a secret falls back to a default instead of being configured.
CHAT_JWT_SECRET_IS_FALLBACK = False
CHAT_SERVICE_KEY_IS_FALLBACK = False


# --- validation ------------------------------------------------------------
# In production, chat secrets must be set explicitly. Anywhere else, fall back
# to JWT_SECRET_KEY so `runserver` works without extra setup — a developer who
# has not configured the gateway still gets working REST endpoints, and the
# realtime layer simply has nothing to connect to.
_environment = os.getenv("DJANGO_ENVIRONMENT", "development")

if CHAT_ENABLED and _environment in ("production", "demo"):
    _missing = [
        name
        for name, value in (
            ("CHAT_JWT_SECRET", CHAT_JWT_SECRET),
            ("CHAT_SERVICE_KEY", CHAT_SERVICE_KEY),
        )
        if not value
    ]
    if _missing:
        raise ValueError(
            f"{', '.join(_missing)} must be set when CHAT_ENABLED is true in "
            f"{_environment}. Generate with `openssl rand -hex 32` and share the "
            "same values with the chat gateway."
        )
    if CHAT_JWT_SECRET == JWT_SECRET_KEY:
        raise ValueError(
            "CHAT_JWT_SECRET must differ from JWT_SECRET_KEY so that a leaked "
            "chat secret cannot be used to mint API sessions."
        )
else:
    # Outside production these fall back so `runserver` works without extra
    # setup — a developer who has not configured the gateway still gets
    # working REST endpoints.
    #
    # The fallbacks are recorded rather than applied silently. A half-
    # configured setup (the gateway has real secrets, Django is still on the
    # placeholders) fails in a genuinely confusing way: the WebSocket
    # handshake succeeds, and then every message, typing event and read
    # receipt is rejected with a 403 the user never sees. The system check in
    # apps/conversations/checks.py turns that into a warning at startup.
    CHAT_JWT_SECRET_IS_FALLBACK = not CHAT_JWT_SECRET
    CHAT_SERVICE_KEY_IS_FALLBACK = not CHAT_SERVICE_KEY

    CHAT_JWT_SECRET = CHAT_JWT_SECRET or JWT_SECRET_KEY
    CHAT_SERVICE_KEY = CHAT_SERVICE_KEY or CHAT_DEV_SERVICE_KEY_PLACEHOLDER
