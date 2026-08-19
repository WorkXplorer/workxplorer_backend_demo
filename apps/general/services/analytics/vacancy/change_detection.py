"""
Vacancy change detection logic for HR Analytics.
Finds all vacancies for a company that had any changes today.
"""

from typing import List
from django.db.models import Q
from django.utils import timezone
from apps.vacancies.models import Vacancy, VacancyView
from apps.applications.models import JobApplication as Application


def get_vacancies_changed_today(company_id: str) -> List[Vacancy]:
    """
    Get all vacancies for a company that had any changes today.
    Uses local timezone date to ensure correct date matching with database queries.
    """
    # Use localtime to get correct local date (Django converts to TIME_ZONE for __date lookups)
    today = timezone.localtime(timezone.now()).date()
    # Get vacancy IDs from vacancies created/updated today
    vacancy_ids_from_vacancy = set(
        Vacancy.objects.filter(
            company_id=company_id
        ).filter(
            Q(created_at__date=today) | Q(updated_at__date=today)
        ).values_list('id', flat=True)
    )
    # Get vacancy IDs from applications changed today
    vacancy_ids_from_applications = set(
        Application.objects.filter(
            vacancy__company_id=company_id
        ).filter(
            Q(applied_at__date=today) |
            Q(updated_at__date=today) |
            Q(hired_at__date=today)
        ).values_list('vacancy_id', flat=True).distinct()
    )
    # Get vacancy IDs from views recorded today
    vacancy_ids_from_views = set(
        VacancyView.objects.filter(
            vacancy__company_id=company_id,
            session_start__date=today
        ).values_list('vacancy_id', flat=True).distinct()
    )
    # Combine all vacancy IDs
    all_vacancy_ids = (
            vacancy_ids_from_vacancy |
            vacancy_ids_from_applications |
            vacancy_ids_from_views
    )
    if not all_vacancy_ids:
        return []
    vacancies = Vacancy.objects.filter(
        id__in=all_vacancy_ids
    ).select_related(
        'domain',
        'created_by',  # Recruiter extends CustomUser, no separate user field
    ).prefetch_related(
        'company__companyprofile',
    ).order_by('-updated_at')
    return list(vacancies)
