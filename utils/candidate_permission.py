from rest_framework.permissions import BasePermission


class IsCandidatePermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and getattr(user, "is_candidate", False)


class IsCandidateOrRecruiterPermission(BasePermission):
    """Allow candidates and recruiters (both submit skills for approval)."""

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (
            getattr(user, "is_candidate", False)
            or getattr(user, "is_recruiter", False)
        )
