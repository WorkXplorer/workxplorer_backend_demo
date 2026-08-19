"""
Time to hire metric for a vacancy.
"""
from typing import Any, Dict
from apps.applications.models import JobApplication as Application
from apps.general.services.analytics.utils import serialize_value
from apps.general.services.analytics.status_helpers import get_hired_status_keys


def calculate_vacancy_time_to_hire(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate time-to-hire data for a specific vacancy.
    
    Uses the HIRED category to support custom statuses that represent
    a hired candidate (not just hardcoded OFFER_ACCEPTED).
    """
    # Get company from vacancy for category lookup
    from apps.vacancies.models import Vacancy
    try:
        vacancy = Vacancy.objects.select_related('company').get(id=vacancy_id)
    except Vacancy.DoesNotExist:
        # Vacancy does not exist: no time-to-hire data can be computed
        return {
            "hired_count": 0,
            "total_days_to_hire": 0,
            "hire_records": [],
        }
    company_id = vacancy.company_id
    
    # Get all status keys that represent "hired" for this company
    hired_status_keys = get_hired_status_keys(company_id)
    
    hired_applications = Application.objects.filter(
        vacancy_id=vacancy_id,
        status__in=hired_status_keys,
        hired_at__isnull=False
    ).select_related('candidate')
    hire_records = []
    total_days_to_hire = 0
    for app in hired_applications:
        if app.applied_at and app.hired_at:
            days_to_hire = (app.hired_at.date() - app.applied_at.date()).days
            if days_to_hire < 0:
                days_to_hire = 0
            hire_records.append({
                "application_id": str(app.id),
                "applied_at": serialize_value(app.applied_at),
                "hired_at": serialize_value(app.hired_at),
                "days_to_hire": days_to_hire,
            })
            total_days_to_hire += days_to_hire
    return {
        "hired_count": len(hire_records),
        "total_days_to_hire": total_days_to_hire,
        "hire_records": hire_records,
    }
