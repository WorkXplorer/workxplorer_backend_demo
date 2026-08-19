"""
Vacancy views metric for a vacancy.
"""
from typing import Any, Dict
from apps.vacancies.models import VacancyView


def calculate_vacancy_views_metric(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate view count for a specific vacancy.
    """
    views_qs = VacancyView.objects.filter(
        vacancy_id=vacancy_id,
        duration_seconds__gte=1,
        duration_seconds__lte=1200,
    ).exclude(duration_seconds__isnull=True)
    total_views = views_qs.count()
    unique_viewers = views_qs.values('candidate').distinct().count()
    return {
        "total_views": total_views,
        "unique_viewers": unique_viewers,
    }
