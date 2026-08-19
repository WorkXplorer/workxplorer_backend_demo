from rest_framework.permissions import IsAuthenticated
from apps.profiles.models import RecruiterProfile
from django.core.cache import cache


class IsRecruiterPermission(IsAuthenticated):
    """
    General permission for any recruiter.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        return getattr(request.user, "is_recruiter", False)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class IsAdminRecruiter(IsRecruiterPermission):
    """
    Permission only for recruiters with admin status
    Optimized with caching to reduce database queries
    """

    def has_permission(self, request, view):
        # First check if the user is recruiter
        if not super().has_permission(request, view):
            return False

        # Cache key for user permissions
        cache_key = f"recruiter_admin_permission_{request.user.id}"

        # Try to get from cache first
        is_admin = cache.get(cache_key)

        if is_admin is None:
            try:
                # Use recruiter_id instead of recruiter instance to avoid
                # multi-table inheritance issues with request.user
                recruiter_profile = RecruiterProfile.objects.get(
                    recruiter_id=request.user.id
                )
                is_admin = recruiter_profile.is_admin

                # Cache for 15 minutes
                cache.set(cache_key, is_admin, 60 * 15)

            except RecruiterProfile.DoesNotExist:
                is_admin = False
                # Cache negative result for shorter time
                cache.set(cache_key, is_admin, 60 * 5)

        return is_admin

    def has_object_permission(self, request, view, obj):
        """Object-level permission check"""
        return self.has_permission(request, view)
