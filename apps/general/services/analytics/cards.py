"""
Dashboard cards analytics for HR Analytics.
Handles the calculation of the 5 main metric cards.

Metrics:
1. Average View Time - How much time candidates spend on job pages
2. Open Vacancies - Number of open jobs at end of period
3. Applications Count - Number of applications received
4. Vacancy Views - Number of job page views
5. Average Candidate Age - Average age of applying candidates
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.authentication.models import Candidate
from apps.vacancies.models import Vacancy, VacancyView
from apps.applications.models import JobApplication as Application

from .utils import calculate_percentage_change, get_period_dates

logger = logging.getLogger(__name__)


def calculate_average_view_time(
        start_date: datetime,
        end_date: datetime,
        vacancy_ids: Optional[List] = None
) -> Dict[str, Any]:
    """
    Calculate average time candidates spend viewing job pages.
    
    Business logic:
    - Include all page views >= 1 second
    - Exclude views > 20 minutes (to avoid skewed data)
    - Each user's multiple views are counted
    
    Args:
        start_date: Start of the analysis period
        end_date: End of the analysis period
        vacancy_ids: Optional list of vacancy IDs to filter by
        
    Returns:
        Dictionary with average view time and total views
    """
    views = VacancyView.objects.filter(
        session_start__range=[start_date, end_date],
        duration_seconds__gte=1,
        duration_seconds__lte=1200,  # 20 minutes max
    ).exclude(duration_seconds__isnull=True)

    if vacancy_ids is not None:
        views = views.filter(vacancy_id__in=vacancy_ids)

    aggregates = views.aggregate(
        total_duration=models.Sum("duration_seconds"),
        view_count=models.Count("id"),
    )
    total_duration = aggregates["total_duration"] or 0
    view_count = aggregates["view_count"] or 0

    if view_count == 0:
        return {
            "average_seconds": 0,
            "total_views": 0,
        }
    average = total_duration / view_count

    return {
        "average_seconds": round(average, 1),
        "total_views": view_count,
    }


def calculate_open_vacancies(
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate number of open vacancies at end of period.
    
    Business logic:
    - Open jobs = status "Open", date <= end of period
    - Compare with previous period
    
    Args:
        end_date: End date of current period
        period_days: Length of period for comparison
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with current count and percentage change
    """
    if end_date is None:
        end_date = timezone.now()

    previous_end_date = end_date - timedelta(days=period_days)

    comparison_data = Vacancy.get_open_vacancies_comparison(
        current_end_date=end_date,
        previous_end_date=previous_end_date,
        company_id=company_id,
    )

    return {
        "current_count": comparison_data["current_count"],
        "previous_count": comparison_data["previous_count"],
        "percentage_change": comparison_data["percentage_change"],
        "absolute_change": comparison_data["absolute_change"],
    }


def calculate_applications_count(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate number of applications received in period.
    
    Business logic:
    - Count all candidate applications in selected period
    - Compare with previous period
    
    Args:
        start_date: Start of current period
        end_date: End of current period
        period_days: Length of period
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with current count and percentage change
    """
    period_dates = get_period_dates(end_date, period_days)

    if start_date is None:
        start_date = period_dates["current_start"]
    if end_date is None:
        end_date = period_dates["current_end"]

    # Current period
    current_qs = Application.objects.filter(applied_at__range=[start_date, end_date])
    if company_id is not None:
        current_qs = current_qs.filter(vacancy__company_id=company_id)
    current_count = current_qs.count()

    # Previous period
    previous_qs = Application.objects.filter(
        applied_at__range=[period_dates["previous_start"], period_dates["previous_end"]]
    )
    if company_id is not None:
        previous_qs = previous_qs.filter(vacancy__company_id=company_id)
    previous_count = previous_qs.count()

    return {
        "current_count": current_count,
        "previous_count": previous_count,
        "percentage_change": calculate_percentage_change(current_count, previous_count),
        "absolute_change": current_count - previous_count,
    }


def calculate_vacancy_views(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        vacancy_ids: Optional[List] = None,
        unique_visitors_only: bool = True
) -> Dict[str, Any]:
    """
    Calculate vacancy views count.
    
    Business logic:
    - Count page view events in period
    - Can count unique visitors or total events
    - Exclude sessions > 20 minutes
    
    Args:
        start_date: Start of current period
        end_date: End of current period
        period_days: Length of period
        vacancy_ids: Optional list of vacancy IDs to filter by
        unique_visitors_only: Whether to count unique visitors only
        
    Returns:
        Dictionary with view counts and metrics
    """
    period_dates = get_period_dates(end_date, period_days)

    if start_date is None:
        start_date = period_dates["current_start"]
    if end_date is None:
        end_date = period_dates["current_end"]

    # Current period views
    current_views_qs = VacancyView.objects.filter(
        session_start__range=[start_date, end_date],
        duration_seconds__gte=1,
        duration_seconds__lte=1200,
    ).exclude(duration_seconds__isnull=True)

    if vacancy_ids is not None:
        current_views_qs = current_views_qs.filter(vacancy_id__in=vacancy_ids)

    # Previous period views
    previous_views_qs = VacancyView.objects.filter(
        session_start__range=[period_dates["previous_start"], period_dates["previous_end"]],
        duration_seconds__gte=1,
        duration_seconds__lte=1200,
    ).exclude(duration_seconds__isnull=True)

    if vacancy_ids is not None:
        previous_views_qs = previous_views_qs.filter(vacancy_id__in=vacancy_ids)

    if unique_visitors_only:
        current_count = current_views_qs.values("vacancy", "candidate").distinct().count()
        previous_count = previous_views_qs.values("vacancy", "candidate").distinct().count()
    else:
        current_count = current_views_qs.count()
        previous_count = previous_views_qs.count()

    # Additional metrics
    current_unique_viewers = current_views_qs.values("candidate").distinct().count()

    return {
        "current_count": current_count,
        "previous_count": previous_count,
        "percentage_change": calculate_percentage_change(current_count, previous_count),
        "absolute_change": current_count - previous_count,
        "unique_viewers": current_unique_viewers,
    }


def calculate_average_candidate_age(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate average age of candidates who applied in period.
    
    Business logic:
    - Average age of candidates who were active in the period
    - Exclude candidates without birthdate
    
    Args:
        start_date: Start of current period
        end_date: End of current period
        period_days: Length of period
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with average age and change metrics
    """
    period_dates = get_period_dates(end_date, period_days)

    if start_date is None:
        start_date = period_dates["current_start"]
    if end_date is None:
        end_date = period_dates["current_end"]

    # Current period applications
    current_applications_qs = Application.objects.filter(
        applied_at__range=[start_date, end_date]
    )
    if company_id is not None:
        current_applications_qs = current_applications_qs.filter(
            vacancy__company_id=company_id
        )

    current_candidate_ids = list(
        current_applications_qs.values_list("candidate_id", flat=True).distinct()
    )

    # Calculate current period ages
    current_ages = []
    current_candidates_with_birthdate = 0

    if current_candidate_ids:
        end_date_for_age = end_date.date() if isinstance(end_date, datetime) else end_date
        for dob in Candidate.objects.filter(id__in=current_candidate_ids).values_list(
                "date_of_birth", flat=True
        ):
            if dob:
                current_ages.append(relativedelta(end_date_for_age, dob).years)
                current_candidates_with_birthdate += 1

    current_avg_age = (
        round(sum(current_ages) / len(current_ages), 1) if current_ages else None
    )

    # Previous period applications
    previous_applications_qs = Application.objects.filter(
        applied_at__range=[period_dates["previous_start"], period_dates["previous_end"]]
    )
    if company_id is not None:
        previous_applications_qs = previous_applications_qs.filter(
            vacancy__company_id=company_id
        )

    previous_candidate_ids = list(
        previous_applications_qs.values_list("candidate_id", flat=True).distinct()
    )

    # Calculate previous period ages
    previous_ages = []

    if previous_candidate_ids:
        previous_end_for_age = (
            period_dates["previous_end"].date()
            if isinstance(period_dates["previous_end"], datetime)
            else period_dates["previous_end"]
        )
        for dob in Candidate.objects.filter(id__in=previous_candidate_ids).values_list(
                "date_of_birth", flat=True
        ):
            if dob:
                previous_ages.append(relativedelta(previous_end_for_age, dob).years)

    previous_avg_age = (
        round(sum(previous_ages) / len(previous_ages), 1) if previous_ages else None
    )

    # Calculate age change
    age_change = None
    if previous_avg_age is not None and current_avg_age is not None:
        age_change = round(current_avg_age - previous_avg_age, 1)

    return {
        "current_average_age": current_avg_age,
        "previous_average_age": previous_avg_age,
        "age_change": age_change,
        "candidates_with_birthdate": current_candidates_with_birthdate,
    }


def get_all_cards_metrics(
        start_date: datetime,
        end_date: datetime,
        period_days: int = 30,
        company_id: Optional[str] = None,
        vacancy_ids: Optional[List] = None
) -> Dict[str, Any]:
    """
    Calculate all 5 dashboard card metrics.
    
    Args:
        start_date: Start of the analysis period
        end_date: End of the analysis period
        period_days: Length of period for comparison
        company_id: Optional company ID to filter by
        vacancy_ids: Optional list of vacancy IDs for view metrics
        
    Returns:
        Dictionary with all 5 card metrics formatted for protobuf
    """
    # Calculate each metric
    avg_view_time = calculate_average_view_time(start_date, end_date, vacancy_ids)
    open_vacancies = calculate_open_vacancies(end_date, period_days, company_id)
    applications = calculate_applications_count(start_date, end_date, period_days, company_id)
    views = calculate_vacancy_views(start_date, end_date, period_days, vacancy_ids)
    avg_age = calculate_average_candidate_age(start_date, end_date, period_days, company_id)

    return {
        "average_view_time": {
            "value": avg_view_time.get("average_seconds", 0),
            "unit": "seconds",
            "label": "Ср. время просмотра вакансий",
            "total_views": avg_view_time.get("total_views", 0),
        },
        "open_vacancies": {
            "value": open_vacancies.get("current_count", 0),
            "label": "Открытые вакансии",
            "percentage_change": open_vacancies.get("percentage_change"),
        },
        "applications_count": {
            "value": applications.get("current_count", 0),
            "label": "Количество откликов",
            "percentage_change": applications.get("percentage_change"),
        },
        "vacancy_views": {
            "value": views.get("current_count", 0),
            "label": "Количество просмотров вакансий",
            "percentage_change": views.get("percentage_change"),
            "unique_viewers": views.get("unique_viewers", 0),
        },
        "average_candidate_age": {
            "value": avg_age.get("current_average_age"),
            "unit": "years",
            "label": "Средний возраст кандидатов",
            "age_change": avg_age.get("age_change"),
        },
    }
