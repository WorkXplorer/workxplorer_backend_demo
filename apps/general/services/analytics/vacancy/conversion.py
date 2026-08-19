"""
Overall conversion metric for a vacancy.
"""
from typing import Any, Dict
from apps.applications.models import JobApplication as Application
from apps.general.services.analytics.status_helpers import get_hired_status_keys


def calculate_vacancy_conversion(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate conversion data for a specific vacancy.
    
    Uses the HIRED category to support custom statuses that represent
    a hired candidate (not just hardcoded OFFER_ACCEPTED).
    """
    # Get company from vacancy for category lookup
    from apps.vacancies.models import Vacancy
    try:
        vacancy = Vacancy.objects.select_related('company').get(id=vacancy_id)
        company_id = vacancy.company_id
    except Vacancy.DoesNotExist:
        company_id = None
    
    # Get all status keys that represent "hired" for this company.
    # If the vacancy (and thus company) does not exist, avoid a cross-company lookup
    # by not calling get_hired_status_keys with a None company_id.
    if company_id is None:
        hired_status_keys = []
    else:
        hired_status_keys = get_hired_status_keys(company_id)
    
    total_applications = Application.objects.filter(
        vacancy_id=vacancy_id
    ).count()
    total_hired = Application.objects.filter(
        vacancy_id=vacancy_id,
        status__in=hired_status_keys
    ).count()
    return {
        "total_applications": total_applications,
        "total_hired": total_hired,
    }
