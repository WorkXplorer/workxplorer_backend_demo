"""
Builds the complete analytics data for a single vacancy and for all changed vacancies of a company.
"""
import logging
from typing import Any, Dict, List
from apps.vacancies.models import Vacancy
from .change_detection import get_vacancies_changed_today
from .cards import get_vacancy_cards

logger = logging.getLogger(__name__)


def _get_company_address(vacancy: Vacancy) -> str:
    """Get company address from company profile."""
    try:
        profiles = vacancy.company.companyprofile.all()
        if profiles:
            return profiles[0].address or ""
    except AttributeError as exc:
        logger.warning(
            "Missing company profile relationship for vacancy %s: %s",
            vacancy.id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error fetching company address for vacancy %s: %s",
            vacancy.id,
            exc,
            exc_info=True,
        )
    return ""


def build_vacancy_analytics_data(vacancy: Vacancy) -> Dict[str, Any]:
    """
    Build complete analytics data for a single vacancy.
    """
    vacancy_id = str(vacancy.id)
    created_by_email = ""
    # Recruiter extends CustomUser directly, so created_by IS the user
    if vacancy.created_by:
        created_by_email = vacancy.created_by.email or ""
    vacancy_data = {
        "id": vacancy_id,
        "title": vacancy.title,
        "domain_id": str(vacancy.domain.id) if vacancy.domain else "",
        "domain": vacancy.domain.name if vacancy.domain else "",
        "created_at": str(vacancy.created_at),
        "updated_at": str(vacancy.updated_at),
        "created_by_email": created_by_email,
        "employment_type": vacancy.employment_type or "",
        "employment_format": vacancy.employment_format or "",
        "company_address": _get_company_address(vacancy),
        "is_active": vacancy.is_active,
        "number_of_positions": vacancy.number_of_positions or 1,
        "salary_min": str(vacancy.salary_min) if vacancy.salary_min else "",
        "salary_max": str(vacancy.salary_max) if vacancy.salary_max else "",
        "salary_currency": vacancy.salary_currency or "",
        "cards": get_vacancy_cards(vacancy_id),
    }
    return vacancy_data


def get_company_vacancies_analytics(company_id: str) -> List[Dict[str, Any]]:
    """
    Get analytics data for all vacancies of a company that changed today.
    """
    vacancies = get_vacancies_changed_today(company_id)
    if not vacancies:
        return []
    vacancies_analytics = []
    for vacancy in vacancies:
        try:
            vacancy_data = build_vacancy_analytics_data(vacancy)
            vacancies_analytics.append(vacancy_data)
        except Exception:
            continue
    return vacancies_analytics
