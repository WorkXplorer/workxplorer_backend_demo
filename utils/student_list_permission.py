from hmac import compare_digest

from rest_framework.permissions import BasePermission
from django.conf import settings


class IsEduPartnerService(BasePermission):
    def has_permission(self, request, view):
        key = settings.EDUPARTNER_SERVICE_KEY
        if not key:
            return False
        return compare_digest(request.headers.get("X-SERVICE-KEY", ""), key)