"""Startup checks for the realtime chat configuration.

A half-configured chat setup fails in a uniquely confusing way: the gateway
and the platform agree on the ticket secret, so the WebSocket handshake
succeeds and the client looks connected — and then every message, typing
event and read receipt is silently rejected with a 403 the user never sees.

These checks turn that into a warning at startup, where it is cheap to fix.
"""

from django.conf import settings
from django.core.checks import Warning as CheckWarning, register


W_SERVICE_KEY_FALLBACK = "conversations.W001"
W_JWT_SECRET_FALLBACK = "conversations.W002"


@register()
def check_chat_secrets(app_configs, **kwargs):
    """Warn when chat is enabled but its secrets were never configured."""
    if not getattr(settings, "CHAT_ENABLED", False):
        return []

    issues = []

    if getattr(settings, "CHAT_SERVICE_KEY_IS_FALLBACK", False):
        issues.append(
            CheckWarning(
                "CHAT_SERVICE_KEY is not set; using the development placeholder.",
                hint=(
                    "The gateway will not be able to persist messages: its calls "
                    "will be rejected with 403 while the WebSocket handshake still "
                    "succeeds, which looks like the socket working but nothing "
                    "sending. Set CHAT_SERVICE_KEY to the same value the gateway "
                    "uses (see .env.chat.example), then restart this process — a "
                    "running container keeps the environment it booted with."
                ),
                id=W_SERVICE_KEY_FALLBACK,
            )
        )

    if getattr(settings, "CHAT_JWT_SECRET_IS_FALLBACK", False):
        issues.append(
            CheckWarning(
                "CHAT_JWT_SECRET is not set; falling back to JWT_SECRET_KEY.",
                hint=(
                    "Connection tickets are being signed with the platform's own "
                    "JWT key. Set a distinct CHAT_JWT_SECRET, matching the "
                    "gateway's, so a leaked chat secret cannot mint API sessions."
                ),
                id=W_JWT_SECRET_FALLBACK,
            )
        )

    return issues
