"""
Hiring dynamics analytics for HR Analytics.
Tracks new hires over time for chart visualization.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from apps.applications.models import JobApplication as Application

from .utils import serialize_value, get_period_dates

logger = logging.getLogger(__name__)


def calculate_hiring_dynamics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        interval: str = "day",
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate hiring dynamics for chart visualization.
    
    Business logic:
    - "Hire" = candidate moved to final status (Hired / Offer Accepted)
    - X-axis = dates (days/weeks/months)
    - Y-axis = count of new hires
    - Support comparison with previous period
    
    Args:
        start_date: Start of current period
        end_date: End of current period
        period_days: Length of period
        interval: 'day', 'week', or 'month' for data aggregation
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with hiring dynamics data
    """
    period_dates = get_period_dates(end_date, period_days)

    if start_date is None:
        start_date = period_dates["current_start"]
    if end_date is None:
        end_date = period_dates["current_end"]

    # Get hiring dynamics using HiringAnalyticsService
    from apps.applications.services.hiring_analytics_service import HiringAnalyticsService
    dynamics_data = HiringAnalyticsService.get_hiring_dynamics_data(
        end_date=end_date,
        period_days=period_days,
        interval=interval,
        company_id=company_id,
    )

    # Transform to protobuf-compatible format
    current_period_obj = dynamics_data.get("current_period", {})
    previous_period_obj = dynamics_data.get("previous_period", {})
    data_interval = dynamics_data.get("meta", {}).get("interval", interval)

    current_period_data = []
    for point in current_period_obj.get("data_points", []):
        current_period_data.append({
            "date": point.get("date"),
            "hires": point.get("count", 0),
            "interval": data_interval,
        })

    previous_period_data = []
    for point in previous_period_obj.get("data_points", []):
        previous_period_data.append({
            "date": point.get("date"),
            "hires": point.get("count", 0),
            "interval": data_interval,
        })

    return {
        "metric_name": "hiring_dynamics",
        "current_period_start": serialize_value(start_date),
        "current_period_end": serialize_value(end_date),
        "previous_period_start": serialize_value(period_dates["previous_start"]),
        "previous_period_end": serialize_value(period_dates["previous_end"]),
        "current_period": current_period_data,
        "previous_period": previous_period_data,
    }


def get_hiring_summary(
        start_date: datetime,
        end_date: datetime,
        company_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get a summary of hiring metrics for the period.
    
    Args:
        start_date: Start of the period
        end_date: End of the period
        company_id: Optional company ID to filter by
        
    Returns:
        Dictionary with summary metrics
    """
    from .status_helpers import get_hired_status_keys

    # Get all status keys that represent "hired" candidates
    # This supports both default and custom statuses mapped to HIRED category
    hired_status_keys = get_hired_status_keys(company_id)

    hires_qs = Application.objects.filter(
        status__in=hired_status_keys,
        updated_at__range=[start_date, end_date],
        is_active=True,
    )

    if company_id is not None:
        hires_qs = hires_qs.filter(vacancy__company_id=company_id)

    total_hires = hires_qs.count()

    return {
        "total_hires": total_hires,
        "period_start": serialize_value(start_date),
        "period_end": serialize_value(end_date),
    }
