import logging
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from apps.applications.models import JobApplication
from apps.applications.models.choices import ApplicationStatus
from apps.authentication.models import Candidate

logger = logging.getLogger(__name__)


def _resolve_candidate_from_request(request):
    target = getattr(request, "_request", request)
    cached = getattr(target, "_candidate_cache", None)
    if cached is not None:
        return cached

    if getattr(target, "_candidate_resolved", False):
        return None

    user = request.user
    candidate = user if isinstance(user, Candidate) else getattr(user, "candidate", None)

    if candidate is None and getattr(user, "email", None):
        candidate = Candidate.objects.filter(email=user.email).first()

    target._candidate_resolved = True
    if candidate is not None:
        target._candidate_cache = candidate

    return candidate


def _with_application_counts(queryset):
    total_applications_subquery = (
        JobApplication.objects.filter(vacancy_id=OuterRef("pk"))
        .values("vacancy_id")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )

    applied_applications_subquery = (
        JobApplication.objects.filter(
            vacancy_id=OuterRef("pk"),
            status=ApplicationStatus.APPLIED,
        )
        .values("vacancy_id")
        .annotate(total=Count("id"))
        .values("total")[:1]
    )

    return queryset.annotate(
        applications_count_value=Coalesce(
            Subquery(total_applications_subquery, output_field=IntegerField()),
            0,
        ),
        applied_applications_count=Coalesce(
            Subquery(applied_applications_subquery, output_field=IntegerField()),
            0,
        ),
    )
