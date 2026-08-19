from rest_framework.permissions import BasePermission
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger(__name__)


class IsCompanyApproved(BasePermission):
    """
    Checks that the recruiter's company has been approved by admin (company.is_active=True).

    Blocks unapproved companies from:
    - Creating vacancies
    - Adding new recruiters
    - Changing kanban application statuses
    - Approving or rejecting candidate applications
    """

    message = _(
        "Your company is pending approval. "
        "This action will be available once your company is approved by the platform admin."
    )

    def has_permission(self, request, view):
        if not getattr(request.user, "is_recruiter", False):
            return False

        try:
            from apps.subscriptions.permissions import get_cached_recruiter, set_cached_recruiter

            recruiter = get_cached_recruiter(request)

            if recruiter is None:
                from apps.authentication.models import Recruiter

                recruiter = Recruiter.objects.select_related("company").get(
                    email=request.user.email
                )
                set_cached_recruiter(request, recruiter)

            if recruiter.company is None:
                return False

            return recruiter.company.is_active

        except Exception:
            logger.exception("IsCompanyApproved permission check failed")
            return False
