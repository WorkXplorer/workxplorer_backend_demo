"""
View mixins for common patterns across views.

These mixins use request-level caching to prevent cross-request data leakage
in concurrent environments. The cache is stored on the **underlying Django
HttpRequest** (``request._request``) rather than the DRF Request wrapper to
ensure it survives DRF request cloning (used by ``BrowsableAPIRenderer``).
"""

from django.http import Http404
from apps.authentication.models import Candidate, Recruiter
from apps.subscriptions.permissions import (
    get_cached_recruiter,
    set_cached_recruiter,
    _cache_target,
)


class CandidateMixin:
    """
    Mixin to provide cached get_candidate method.
    Uses request-level caching to prevent cross-request data leakage.
    """

    def get_candidate(self):
        """
        Extract and cache the candidate instance.
        Prevents multiple DB hits for the same candidate in one request.
        Cache is stored on the underlying Django request for thread safety
        and clone resilience.
        """
        target = _cache_target(self.request)

        cached = getattr(target, '_candidate_cache', None)
        if cached is not None:
            return cached

        user = self.request.user

        if not user.is_candidate:
            raise Http404("Only candidates can access this resource")

        try:
            candidate = Candidate.objects.get(email=user.email)
            setattr(target, '_candidate_cache', candidate)
            return candidate
        except Candidate.DoesNotExist:
            raise Http404("Candidate profile not found")


class RecruiterMixin:
    """
    Mixin to provide get_recruiter method for views that need recruiter info.
    Includes request-level caching to prevent duplicate DB queries within a single request
    and avoid cross-request data leakage in concurrent environments.

    The cache is stored on the underlying Django ``HttpRequest`` so it is
    shared with the subscription permission cache and survives DRF request
    cloning by ``BrowsableAPIRenderer``.
    """

    def get_recruiter(self):
        """
        Extract and return the recruiter instance from the authenticated user.
        Caches the recruiter on the underlying Django request to avoid
        multiple DB hits in a single request.

        Raises:
            Http404: If user is not a recruiter or recruiter doesn't exist
        """
        # Check for cached recruiter (shared with subscription permission layer)
        cached = get_cached_recruiter(self.request)
        if cached is not None:
            return cached

        user = self.request.user

        if not user.is_recruiter:
            raise Http404("Only recruiters can access this resource")

        if isinstance(user, Recruiter):
            recruiter = user
            company = getattr(recruiter, "company", None)
            if company is None:
                recruiter = Recruiter.objects.select_related("company").get(pk=user.pk)
            set_cached_recruiter(self.request, recruiter)
            return recruiter

        try:
            recruiter = Recruiter.objects.select_related(
                "company"
            ).get(pk=user.pk)
            set_cached_recruiter(self.request, recruiter)
            return recruiter
        except Recruiter.DoesNotExist:
            raise Http404("Recruiter profile not found")


class RecruiterCompanyMixin(RecruiterMixin):
    """
    Mixin to provide get_recruiter_and_company method for views that need both.
    Extends RecruiterMixin to also return company information.
    """

    def get_recruiter_and_company(self):
        """
        Extract recruiter and company from the authenticated user.

        Returns:
            Tuple of (recruiter, company)

        Raises:
            Http404: If user is not a recruiter, recruiter doesn't exist,
                     or recruiter has no associated company
        """
        recruiter = self.get_recruiter()

        if not recruiter.company:
            raise Http404("Recruiter has no associated company")

        return recruiter, recruiter.company
