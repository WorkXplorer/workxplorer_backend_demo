# Vacancy analytics package

from .build import get_company_vacancies_analytics, build_vacancy_analytics_data
from .cards import get_vacancy_cards
from .change_detection import get_vacancies_changed_today
from .time_to_hire import calculate_vacancy_time_to_hire
from .conversion import calculate_vacancy_conversion
from .views import calculate_vacancy_views_metric
from .applications import calculate_vacancy_applications_metric
from .average_age import calculate_vacancy_average_age
from .response_funnel import calculate_vacancy_response_funnel
from .top_skills import calculate_vacancy_top_skills

__all__ = [
    'get_company_vacancies_analytics',
    'build_vacancy_analytics_data',
    'get_vacancy_cards',
    'get_vacancies_changed_today',
    'calculate_vacancy_time_to_hire',
    'calculate_vacancy_conversion',
    'calculate_vacancy_views_metric',
    'calculate_vacancy_applications_metric',
    'calculate_vacancy_average_age',
    'calculate_vacancy_response_funnel',
    'calculate_vacancy_top_skills',
]
