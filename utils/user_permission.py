from rest_framework.permissions import BasePermission


class IsSelfPermission(BasePermission):
    """
    Allows access only to the authenticated user for their own object.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return obj == request.user
