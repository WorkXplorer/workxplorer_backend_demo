"""
Popular industries analytics for EduPartner analytics data.
Handles the calculation of industry demand and time-series data.
"""

import logging
from collections import defaultdict

from django.db.models import Sum
from django.db.models.functions import TruncMonth, TruncDay

from apps.vacancies.models import Vacancy
from apps.domain.models import Domain
from utils.fill_missing_dates import (
    fill_daily_data,
    fill_monthly_data,
    get_current_month_range,
    get_current_year_range,
    get_last_7_days_range,
)

logger = logging.getLogger(__name__)


# Period constants
PERIOD_7_DAYS = "7_days"
PERIOD_30_DAYS = "30_days"
PERIOD_12_MONTHS = "12_months"


def get_popular_industries(faculty_domain_ids: list) -> dict:
    """
    Get popular industries data for time-series chart.
    
    Fills in missing dates with zero values to ensure complete time series.
    
    - 7_days: Last 7 days including today
    - 30_days: Current month (from 1st to today)
    - 12_months: Current year (from January to current month)
    
    Args:
        faculty_domain_ids: List of domain IDs related to faculties
        
    Returns:
        dict: Popular industries data organized by period (7_days, 30_days, 12_months)
    """
    # Get domain names for filling empty data
    domain_names = _get_domain_names(faculty_domain_ids) if faculty_domain_ids else {}
    domain_ids_str = [str(did) for did in faculty_domain_ids] if faculty_domain_ids else []

    # Define date ranges
    # 7 days: Last 7 days including today
    seven_days_start, seven_days_end = get_last_7_days_range()

    # 30 days (current month): From 1st of current month to today
    month_start, month_end = get_current_month_range()

    # 12 months (current year): From January to current month
    year_start, year_end = get_current_year_range()

    # Get raw data from database
    raw_7_days = []
    raw_30_days = []
    raw_12_months = []

    if faculty_domain_ids:
        raw_7_days = _get_industry_data_daily(
            faculty_domain_ids, seven_days_start, seven_days_end
        )
        raw_30_days = _get_industry_data_daily(
            faculty_domain_ids, month_start, month_end
        )
        raw_12_months = _get_industry_data_monthly(
            faculty_domain_ids, year_start, year_end
        )

    # Fill missing dates for each period
    result = {
        PERIOD_7_DAYS: fill_daily_data(
            raw_7_days,
            seven_days_start,
            seven_days_end,
            domain_ids=domain_ids_str,
            domain_names=domain_names,
        ),
        PERIOD_30_DAYS: fill_daily_data(
            raw_30_days,
            month_start,
            month_end,
            domain_ids=domain_ids_str,
            domain_names=domain_names,
        ),
        PERIOD_12_MONTHS: fill_monthly_data(
            raw_12_months,
            year_start,
            year_end,
            domain_ids=domain_ids_str,
            domain_names=domain_names,
        ),
    }

    return result


def _get_domain_names(domain_ids: list) -> dict:
    """
    Get domain names for the given domain IDs.
    
    Args:
        domain_ids: List of domain IDs
        
    Returns:
        dict: Mapping of domain_id (str) to domain_name
    """
    if not domain_ids:
        return {}

    domains = Domain.objects.filter(id__in=domain_ids).values("id", "name")
    return {str(d["id"]): d["name"] for d in domains}


def _get_industry_data_daily(domain_ids: list, start_date, end_date) -> list:
    """
    Get daily industry demand data.
    
    Args:
        domain_ids: List of domain IDs to query
        start_date: Start date for the query range
        end_date: End date for the query range
        
    Returns:
        list: Industry data with daily positions counts
    """
    domains = Domain.objects.filter(id__in=domain_ids).values("id", "name")
    domain_map = {d["id"]: d["name"] for d in domains}

    vacancies_data = (
        Vacancy.objects.filter(
            domain_id__in=domain_ids,
            is_active=True,
            created_at__gte=start_date,
            created_at__lte=end_date,
        )
        .annotate(day=TruncDay("created_at"))
        .values("domain_id", "day")
        .annotate(total_positions=Sum("number_of_positions"))
        .order_by("day")
    )

    domain_data = defaultdict(lambda: {"name": "", "data": []})

    for item in vacancies_data:
        domain_id = item["domain_id"]
        domain_name = domain_map.get(domain_id, "Unknown")

        domain_data[domain_id]["name"] = domain_name
        domain_data[domain_id]["data"].append(
            {
                "date": item["day"].isoformat(),
                "positions": item["total_positions"] or 0,
            }
        )

    result = []
    for domain_id, data in domain_data.items():
        result.append(
            {
                "domain_id": str(domain_id),
                "domain_name": data["name"],
                "daily_data": data["data"],
            }
        )

    return result


def _get_industry_data_monthly(domain_ids: list, start_date, end_date) -> list:
    """
    Get monthly industry demand data.
    
    Args:
        domain_ids: List of domain IDs to query
        start_date: Start date for the query range
        end_date: End date for the query range
        
    Returns:
        list: Industry data with monthly positions counts
    """
    domains = Domain.objects.filter(id__in=domain_ids).values("id", "name")
    domain_map = {d["id"]: d["name"] for d in domains}

    vacancies_data = (
        Vacancy.objects.filter(
            domain_id__in=domain_ids,
            is_active=True,
            created_at__gte=start_date,
            created_at__lte=end_date,
        )
        .annotate(month=TruncMonth("created_at"))
        .values("domain_id", "month")
        .annotate(total_positions=Sum("number_of_positions"))
        .order_by("month")
    )

    domain_data = defaultdict(lambda: {"name": "", "data": []})

    for item in vacancies_data:
        domain_id = item["domain_id"]
        domain_name = domain_map.get(domain_id, "Unknown")

        domain_data[domain_id]["name"] = domain_name
        domain_data[domain_id]["data"].append(
            {
                "month": item["month"].strftime("%Y-%m"),
                "month_name": item["month"].strftime("%b"),
                "positions": item["total_positions"] or 0,
            }
        )

    result = []
    for domain_id, data in domain_data.items():
        result.append(
            {
                "domain_id": str(domain_id),
                "domain_name": data["name"],
                "monthly_data": data["data"],
            }
        )

    return result
