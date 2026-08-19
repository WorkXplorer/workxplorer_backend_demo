"""
Response funnel data for vacancy analytics.
Collects raw counts for each stage of the hiring funnel.

Stages:
1. Applications - total applications for the vacancy
2. Invitations - unique candidates invited to next stage
3. Interviews - unique candidates who reached interview status
4. Offers - unique candidates who received an offer

Note: We only send raw counts. Calculations are done by the analytics service.
"""

from typing import Any, Dict

from apps.applications.models import JobApplication as Application
from apps.vacancies.models import VacancyView
from apps.general.services.analytics.status_helpers import (
    get_interviewed_status_keys,
    get_offer_extended_status_keys,
    get_screening_status_keys,
)


def calculate_vacancy_response_funnel(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate response funnel data for a specific vacancy.
    
    Returns raw counts for each funnel stage using status categories
    to support custom statuses:
    - views: total vacancy views (reference for percentage calculation)
    - applications: total applications received
    - invitations: unique candidates invited (SCREENING category and beyond)
    - interviews: unique candidates who were interviewed (INTERVIEWING category and beyond)
    - offers: unique candidates who received an offer (OFFERED, HIRED, OFFER_REJECTED)
    
    Args:
        vacancy_id: UUID string of the vacancy
        
    Returns:
        Dictionary with raw funnel counts
    """
    # Get company from vacancy for category lookup
    from apps.vacancies.models import Vacancy
    try:
        vacancy = Vacancy.objects.select_related('company').get(id=vacancy_id)
        company_id = vacancy.company_id
    except Vacancy.DoesNotExist:
        return {
            "views_count": 0,
            "applications_count": 0,
            "invitations_count": 0,
            "interviews_count": 0,
            "offers_count": 0,
        }
    
    # Views count (reference point for funnel percentages)
    views_count = VacancyView.objects.filter(
        vacancy_id=vacancy_id,
        duration_seconds__gte=1,
        duration_seconds__lte=1200,
    ).exclude(duration_seconds__isnull=True).count()

    # Applications count (all applications)
    applications_count = Application.objects.filter(
        vacancy_id=vacancy_id
    ).count()

    # Get status keys by category for this company
    screening_keys = get_screening_status_keys(company_id)
    interviewed_keys = get_interviewed_status_keys(company_id)
    offer_keys = get_offer_extended_status_keys(company_id)
    
    # Invitations count - unique candidates who reached SCREENING status
    # Plus those who progressed beyond (INTERVIEWING, OFFERED, HIRED)
    # Using category-based lookup for custom statuses
    invitations_in_screening = Application.objects.filter(
        vacancy_id=vacancy_id,
        status__in=screening_keys
    ).values('candidate').distinct().count()

    # Candidates who progressed beyond screening
    interviewed_or_beyond = Application.objects.filter(
        vacancy_id=vacancy_id,
        status__in=interviewed_keys
    ).values('candidate').distinct().count()

    # Candidates who received offers (beyond interviewing)
    offered_or_beyond = Application.objects.filter(
        vacancy_id=vacancy_id,
        status__in=offer_keys
    ).values('candidate').distinct().count()

    # Total invitations = currently at screening + those who progressed beyond
    total_invitations = invitations_in_screening + interviewed_or_beyond

    # Interviews count - unique candidates who reached INTERVIEWED or beyond
    interviews_count = interviewed_or_beyond

    # Offers count - unique candidates who received any offer status
    offers_count = offered_or_beyond

    return {
        "views_count": views_count,
        "applications_count": applications_count,
        "invitations_count": total_invitations,
        "interviews_count": interviews_count,
        "offers_count": offers_count,
    }
