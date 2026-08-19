"""
Applications count metric for a vacancy.
"""
from typing import Any, Dict
from apps.applications.models import JobApplication as Application


def calculate_vacancy_applications_metric(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate application count for a specific vacancy.
    """
    count = Application.objects.filter(vacancy_id=vacancy_id).count()
    return {
        "count": count,
    }
