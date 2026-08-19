"""
Aggregates all vacancy card metrics for a specific vacancy.
"""
from typing import Any, Dict
from .time_to_hire import calculate_vacancy_time_to_hire
from .conversion import calculate_vacancy_conversion
from .views import calculate_vacancy_views_metric
from .applications import calculate_vacancy_applications_metric
from .average_age import calculate_vacancy_average_age
from .response_funnel import calculate_vacancy_response_funnel
from .top_skills import calculate_vacancy_top_skills
from .candidates_by_region import calculate_vacancy_candidates_by_region


def get_vacancy_cards(vacancy_id: str) -> Dict[str, Any]:
    """
    Get all card metrics for a specific vacancy.
    """
    return {
        "time_to_hire": calculate_vacancy_time_to_hire(vacancy_id),
        "conversion": calculate_vacancy_conversion(vacancy_id),
        "views": calculate_vacancy_views_metric(vacancy_id),
        "applications": calculate_vacancy_applications_metric(vacancy_id),
        "average_age": calculate_vacancy_average_age(vacancy_id),
        "response_funnel": calculate_vacancy_response_funnel(vacancy_id),
        "top_skills": calculate_vacancy_top_skills(vacancy_id),
        "candidates_by_region": calculate_vacancy_candidates_by_region(vacancy_id),
    }
