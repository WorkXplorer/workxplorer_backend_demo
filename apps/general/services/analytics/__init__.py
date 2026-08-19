"""
Analytics module for HR Analytics data collection.
Provides separated components for different analytics aspects.
"""

from .main import HRAnalyticsService
from .cards import (
    calculate_average_view_time,
    calculate_open_vacancies,
    calculate_applications_count,
    calculate_vacancy_views,
    calculate_average_candidate_age,
    get_all_cards_metrics,
)
from .top_industries import calculate_top_industries, get_all_industries
from .hiring_dynamics import calculate_hiring_dynamics, get_hiring_summary
from .application_dynamics import (
    calculate_application_dynamics_yearly,
    get_monthly_comparison,
)
from .vacancy.change_detection import get_vacancies_changed_today
from .vacancy.time_to_hire import calculate_vacancy_time_to_hire
from .vacancy.conversion import calculate_vacancy_conversion
from .vacancy.views import calculate_vacancy_views_metric
from .vacancy.applications import calculate_vacancy_applications_metric
from .vacancy.average_age import calculate_vacancy_average_age
from .vacancy.cards import get_vacancy_cards
from .vacancy.build import build_vacancy_analytics_data, get_company_vacancies_analytics
from .utils import (
    serialize_value,
    calculate_percentage_change,
    get_period_dates,
    validate_json_payload,
    base_instance_dict,
    # Backward compatibility aliases
    _serialize_value,
    _base_instance_dict,
)
from .protobuf_service import HRAnalyticsProtobufService
from .vacancy_protobuf_service import VacancyAnalyticsProtobufService
from .data_processing import (
    prepare_summary_data,
    get_applications_data,
    get_resumes_data,
    get_vacancies_data,
    get_recent_applications,
    get_recent_resumes,
    get_recent_vacancies,
)

__all__ = [
    # Main service
    "HRAnalyticsService",
    # Card metrics
    "calculate_average_view_time",
    "calculate_open_vacancies",
    "calculate_applications_count",
    "calculate_vacancy_views",
    "calculate_average_candidate_age",
    "get_all_cards_metrics",
    # Top industries
    "calculate_top_industries",
    "get_all_industries",
    # Hiring dynamics
    "calculate_hiring_dynamics",
    "get_hiring_summary",
    # Application dynamics
    "calculate_application_dynamics_yearly",
    "get_monthly_comparison",
    # Vacancy analytics
    "get_vacancies_changed_today",
    "calculate_vacancy_time_to_hire",
    "calculate_vacancy_conversion",
    "calculate_vacancy_views_metric",
    "calculate_vacancy_applications_metric",
    "calculate_vacancy_average_age",
    "get_vacancy_cards",
    "build_vacancy_analytics_data",
    "get_company_vacancies_analytics",
    # Utilities
    "serialize_value",
    "calculate_percentage_change",
    "get_period_dates",
    "validate_json_payload",
    "base_instance_dict",
    "_serialize_value",
    "_base_instance_dict",
    # Protobuf services
    "HRAnalyticsProtobufService",
    "VacancyAnalyticsProtobufService",
    # Data processing
    "prepare_summary_data",
    "get_applications_data",
    "get_resumes_data",
    "get_vacancies_data",
    "get_recent_applications",
    "get_recent_resumes",
    "get_recent_vacancies",
]
