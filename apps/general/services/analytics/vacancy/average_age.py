"""
Average age metric for a vacancy.
"""
from typing import Any, Dict
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from apps.authentication.models import Candidate
from apps.applications.models import JobApplication as Application


def calculate_vacancy_average_age(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate average age data for applicants of a specific vacancy.
    """
    candidate_ids = Application.objects.filter(
        vacancy_id=vacancy_id
    ).values_list('candidate_id', flat=True).distinct()
    candidates_with_dob = Candidate.objects.filter(
        id__in=candidate_ids,
        date_of_birth__isnull=False
    ).values_list('date_of_birth', flat=True)
    today = timezone.now().date()
    total_age_sum = 0
    applicants_with_age = 0
    for dob in candidates_with_dob:
        if dob:
            age = relativedelta(today, dob).years
            total_age_sum += age
            applicants_with_age += 1
    return {
        "applicants_with_age": applicants_with_age,
        "total_age_sum": total_age_sum,
    }
