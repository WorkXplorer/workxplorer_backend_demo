"""
Top companies analytics for EduPartner analytics data.
Handles the calculation of top companies by student placements.
"""

import logging
from django.db.models import Count, Exists, OuterRef

from apps.applications.models import (
    ApplicationStatusModel,
    JobApplication as Application,
    StatusCategory,
)

logger = logging.getLogger(__name__)


def get_top_companies_by_placements(candidate_ids: list, limit: int = 10) -> list:
    """
    Get top companies ranked by number of student placements (hires).

    Args:
        candidate_ids: List of candidate IDs from the edupartner
        limit: Number of top companies to return (default 10)

    Returns:
        list: Top companies with placement counts, ranked by hiring volume
    """
    if not candidate_ids:
        return []

    hired_status_subquery = ApplicationStatusModel.objects.filter(
        company_id=OuterRef('vacancy__company_id'),
        key=OuterRef('status'),
        category__key=StatusCategory.HIRED,
        is_active=True,
    )

    # Get companies that hired students (applications mapped to HIRED category)
    # Count distinct candidates hired per company
    top_companies = (
        Application.objects.filter(
            candidate_id__in=candidate_ids,
            vacancy__company__isnull=False,
            is_active=True,
        )
        .annotate(is_hired_status=Exists(hired_status_subquery))
        .filter(is_hired_status=True)
        .values("vacancy__company_id", "vacancy__company__name")
        .annotate(hired_count=Count("candidate_id", distinct=True))
        .order_by("-hired_count")[:limit]
    )

    result = []
    for rank, company in enumerate(top_companies, start=1):
        result.append(
            {
                "company_id": str(company["vacancy__company_id"]),
                "company_name": company["vacancy__company__name"],
                "hired_count": company["hired_count"],
                "rank": rank,
            }
        )

    return result
