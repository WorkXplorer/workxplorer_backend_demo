"""Permissions for the chat integration."""

import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class IsChatService(BasePermission):
    """Authenticate the Go chat gateway by its shared service key.

    The endpoints behind this permission act on behalf of a user id supplied
    in the request body, so they must be reachable by the gateway and by
    nothing else. Two safeguards apply:

    - The key is compared in constant time, so a wrong key cannot be
      recovered by timing the response.
    - An unset key fails closed. Without this, an empty ``CHAT_SERVICE_KEY``
      would match an empty header and hand every anonymous caller the ability
      to post messages as any user.

    The gateway is expected to reach these endpoints over the private
    network; the key is defence in depth, not the only barrier.
    """

    message = "Invalid chat service credentials."

    def has_permission(self, request, view):
        expected = getattr(settings, "CHAT_SERVICE_KEY", "") or ""
        if not expected:
            return False

        provided = request.headers.get("X-Chat-Service-Key", "") or ""
        return hmac.compare_digest(provided, expected)
