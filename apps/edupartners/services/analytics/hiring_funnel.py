"""
Hiring funnel analytics for EduPartner analytics data.
Handles the calculation of hiring progression statistics.
"""

import logging
from django.db.models import Exists, OuterRef

from apps.resumes.models import Resume
from apps.applications.models import (
    ApplicationStatusModel,
    JobApplication as Application,
    StatusCategory,
)
from apps.general.services.analytics.status_helpers import (
    get_invited_status_keys,
    get_offer_extended_status_keys,
)

logger = logging.getLogger(__name__)


def get_hiring_funnel(candidate_ids: list) -> dict:
    """
    Get hiring funnel data showing the progression from resume creation to hiring.

    Funnel stages:
    1. Resumes Created - Total resumes by edupartner students
    2. Interview Invitations - Applications that reached interview stage
    3. Offers Made - Applications that received job offers
    4. Hired - Applications that resulted in hiring (HIRED category status)

    Args:
        candidate_ids: List of candidate IDs from the edupartner

    Returns:
        dict: Hiring funnel data with counts and conversion rates
    """
    if not candidate_ids:
        return {
            "resumes_created": 0,
            "interviewed": 0,
            "offered": 0,
            "hired": 0,
            "conversion_rates": {
                "resume_to_interview": 0.0,
                "interview_to_offer": 0.0,
                "offer_to_hire": 0.0,
                "overall_conversion": 0.0,
            },
        }

    # Stage 1: Total resumes created by students from this edupartner
    resumes_created = Resume.objects.filter(
        candidate_id__in=candidate_ids, is_active=True
    ).count()

    # Stage 2: Students who were invited to interviews
    # Uses category-based lookup to support custom statuses
    invited_status_keys = get_invited_status_keys()
    interviewed_candidates = (
        Application.objects.filter(
            candidate_id__in=candidate_ids,
            status__in=invited_status_keys,
            is_active=True,
        )
        .values("candidate_id")
        .distinct()
        .count()
    )

    # Stage 3: Students who received offers
    # Uses category-based lookup to support custom statuses
    offer_status_keys = get_offer_extended_status_keys()
    offered_candidates = (
        Application.objects.filter(
            candidate_id__in=candidate_ids,
            status__in=offer_status_keys,
            is_active=True,
        )
        .values("candidate_id")
        .distinct()
        .count()
    )

    # Stage 4: Students who started working (HIRED category status)
    hired_status_subquery = ApplicationStatusModel.objects.filter(
        company_id=OuterRef('vacancy__company_id'),
        key=OuterRef('status'),
        category__key=StatusCategory.HIRED,
        is_active=True,
    )
    hired_candidates = (
        Application.objects.filter(
            candidate_id__in=candidate_ids,
            is_active=True,
        )
        .annotate(is_hired_status=Exists(hired_status_subquery))
        .filter(is_hired_status=True)
        .values("candidate_id")
        .distinct()
        .count()
    )

    # Calculate conversion rates
    conversion_rates = _calculate_conversion_rates(
        resumes_created=resumes_created,
        interviewed=interviewed_candidates,
        offered=offered_candidates,
        hired=hired_candidates,
    )

    return {
        "resumes_created": resumes_created,
        "interviewed": interviewed_candidates,
        "offered": offered_candidates,
        "hired": hired_candidates,
        "conversion_rates": conversion_rates,
    }


def _calculate_conversion_rates(
        resumes_created: int,
        interviewed: int,
        offered: int,
        hired: int,
) -> dict:
    """
    Calculate conversion rates between hiring funnel stages.
    
    Args:
        resumes_created: Total resumes created
        interviewed: Number of candidates interviewed
        offered: Number of candidates who received offers
        hired: Number of candidates hired
        
    Returns:
        dict: Conversion rates between stages
    """
    interview_rate = (
        (interviewed / resumes_created * 100) if resumes_created > 0 else 0
    )
    offer_rate = (
        (offered / interviewed * 100) if interviewed > 0 else 0
    )
    hire_rate = (
        (hired / offered * 100) if offered > 0 else 0
    )
    overall_conversion = (
        (hired / resumes_created * 100) if resumes_created > 0 else 0
    )

    return {
        "resume_to_interview": round(interview_rate, 1),
        "interview_to_offer": round(offer_rate, 1),
        "offer_to_hire": round(hire_rate, 1),
        "overall_conversion": round(overall_conversion, 1),
    }
