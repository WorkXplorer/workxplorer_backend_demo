"""
Application dynamics analytics for HR Analytics.
Calculates monthly application distribution with year-over-year comparison.
"""

import logging
import calendar
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.applications.models import JobApplication as Application

from .utils import serialize_value

logger = logging.getLogger(__name__)


def calculate_application_dynamics_yearly(
        current_year: Optional[int] = None,
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate application response dynamics for current year with previous year comparison.
    
    Business question: How are applications distributed by months of the current year
    and how does this differ from the previous year?
    
    Business logic:
    - Applications by months of the calendar year
    - Always built for 12 months
    - Add comparison with previous year
    
    Args:
        current_year: Year to calculate for (default: current year)
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with monthly data for current and previous year
    """
    if current_year is None:
        current_year = timezone.now().year

    previous_year = current_year - 1

    # Date ranges
    current_year_start = datetime(current_year, 1, 1, tzinfo=dt_timezone.utc)
    current_year_end = datetime(current_year, 12, 31, 23, 59, 59, tzinfo=dt_timezone.utc)
    previous_year_start = datetime(previous_year, 1, 1, tzinfo=dt_timezone.utc)
    previous_year_end = datetime(previous_year, 12, 31, 23, 59, 59, tzinfo=dt_timezone.utc)

    # Current year queryset
    current_year_qs = Application.objects.filter(
        applied_at__range=[current_year_start, current_year_end]
    )
    if company_id:
        current_year_qs = current_year_qs.filter(vacancy__company_id=company_id)

    # Previous year queryset
    previous_year_qs = Application.objects.filter(
        applied_at__range=[previous_year_start, previous_year_end]
    )
    if company_id:
        previous_year_qs = previous_year_qs.filter(vacancy__company_id=company_id)

    # Get monthly data
    current_year_data = (
        current_year_qs.annotate(month=TruncMonth("applied_at"))
        .values("month")
        .annotate(applications_count=Count("id"))
        .order_by("month")
    )

    previous_year_data = (
        previous_year_qs.annotate(month=TruncMonth("applied_at"))
        .values("month")
        .annotate(applications_count=Count("id"))
        .order_by("month")
    )

    # Build monthly series for current year
    current_year_series = _build_monthly_series(
        current_year, current_year_data
    )

    # Build monthly series for previous year
    previous_year_series = _build_monthly_series(
        previous_year, previous_year_data
    )

    # Calculate totals
    current_year_total = sum(item["applications_count"] for item in current_year_series)
    previous_year_total = sum(item["applications_count"] for item in previous_year_series)

    return {
        "metric_name": "application_response_dynamics_yearly",
        "current_year": {
            "year": current_year,
            "start_date": serialize_value(current_year_start),
            "end_date": serialize_value(current_year_end),
            "total_applications": current_year_total,
            "monthly_data": current_year_series,
        },
        "previous_year": {
            "year": previous_year,
            "start_date": serialize_value(previous_year_start),
            "end_date": serialize_value(previous_year_end),
            "total_applications": previous_year_total,
            "monthly_data": previous_year_series,
        },
    }


def _build_monthly_series(year: int, monthly_data: Any) -> List[Dict[str, Any]]:
    """
    Build a complete 12-month series with data.
    
    Args:
        year: The year for the series
        monthly_data: QuerySet with monthly aggregated data
        
    Returns:
        List of 12 month records
    """
    series = []

    for month_num in range(1, 13):
        month_date = datetime(year, month_num, 1, tzinfo=dt_timezone.utc)
        month_name = calendar.month_name[month_num]

        # Find count for this month
        month_count = 0
        for item in monthly_data:
            if item["month"].month == month_num:
                month_count = item["applications_count"]
                break

        series.append({
            "month": month_num,
            "month_name": month_name,
            "year": year,
            "date": month_date.strftime("%Y-%m-%d"),
            "applications_count": month_count,
        })

    return series


def get_monthly_comparison(
        year: int,
        month: int,
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get comparison between a specific month and the same month in previous year.
    
    Args:
        year: The year
        month: The month (1-12)
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with monthly comparison
    """
    current_start = datetime(year, month, 1, tzinfo=dt_timezone.utc)

    # Get last day of month
    _, last_day = calendar.monthrange(year, month)
    current_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=dt_timezone.utc)

    previous_year = year - 1
    previous_start = datetime(previous_year, month, 1, tzinfo=dt_timezone.utc)
    _, prev_last_day = calendar.monthrange(previous_year, month)
    previous_end = datetime(previous_year, month, prev_last_day, 23, 59, 59, tzinfo=dt_timezone.utc)

    # Current month
    current_qs = Application.objects.filter(applied_at__range=[current_start, current_end])
    if company_id:
        current_qs = current_qs.filter(vacancy__company_id=company_id)
    current_count = current_qs.count()

    # Previous year same month
    previous_qs = Application.objects.filter(applied_at__range=[previous_start, previous_end])
    if company_id:
        previous_qs = previous_qs.filter(vacancy__company_id=company_id)
    previous_count = previous_qs.count()

    # Calculate change
    percentage_change = None
    if previous_count > 0:
        percentage_change = round(
            ((current_count - previous_count) / previous_count) * 100, 1
        )

    return {
        "month": month,
        "month_name": calendar.month_name[month],
        "current_year": year,
        "current_count": current_count,
        "previous_year": previous_year,
        "previous_count": previous_count,
        "percentage_change": percentage_change,
    }
