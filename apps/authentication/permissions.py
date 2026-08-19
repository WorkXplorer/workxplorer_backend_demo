from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework.permissions import BasePermission


class IsMobileAppClient(BasePermission):
    """
    Restricts a view to requests carrying the mobile app's shared secret on
    the X-Mobile-App-Key header. Not a substitute for user authentication —
    only a gate keeping the mobile-only auth endpoints from being reachable
    by arbitrary web/API clients.
    """

    def has_permission(self, request, view):
        expected = settings.MOBILE_APP_API_KEY
        if not expected:
            return False

        provided = request.headers.get("X-Mobile-App-Key", "")
        return constant_time_compare(provided, expected)
