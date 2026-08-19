"""
Top industries analytics for HR Analytics.
Calculates which industries receive the most candidate applications.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db.models import Count

from apps.applications.models import JobApplication as Application

from .utils import serialize_value, get_period_dates

logger = logging.getLogger(__name__)


def calculate_top_industries(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        company_id: Optional[str] = None,
        limit: int = 10
) -> Dict[str, Any]:
    """
    Calculate top industries by application count.
    
    Business question: Which industries receive the most candidate applications?
    
    Business logic:
    - Data source is vacancy's industry (domain) field
    - Count all applications in period, group by industry
    - Return top industries with application counts
    
    Args:
        start_date: Start of current period
        end_date: End of current period
        period_days: Length of period
        company_id: Optional company ID to filter by
        limit: Number of top industries to return
        
    Returns:
        Dictionary with top industries and metrics
    """
    period_dates = get_period_dates(end_date, period_days)

    if start_date is None:
        start_date = period_dates["current_start"]
    if end_date is None:
        end_date = period_dates["current_end"]

    # Get applications in the period with vacancy domain information
    applications_qs = Application.objects.filter(
        applied_at__range=[start_date, end_date]
    ).select_related("vacancy__domain")

    if company_id is not None:
        applications_qs = applications_qs.filter(vacancy__company_id=company_id)

    # Group by domain (industry) and count applications
    industry_data = (
        applications_qs.values("vacancy__domain__id", "vacancy__domain__name")
        .annotate(applications_count=Count("id"))
        .order_by("-applications_count")
    )

    # Format the results
    top_industries = []
    total_applications = applications_qs.count()

    for item in industry_data:
        if item["vacancy__domain__id"]:  # Skip null domains
            percentage = (
                (item["applications_count"] / total_applications * 100)
                if total_applications > 0
                else 0
            )
            top_industries.append({
                "industry_id": str(item["vacancy__domain__id"]),
                "industry_name": item["vacancy__domain__name"] or "Unknown",
                "applications_count": item["applications_count"],
                "percentage": round(percentage, 1),
            })

    return {
        "metric_name": "top_industries",
        "period_start": serialize_value(start_date),
        "period_end": serialize_value(end_date),
        "period_days": period_days,
        "total_applications": total_applications,
        "industries": top_industries[:limit],
    }


def get_all_industries(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period_days: int = 30,
        company_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all industries with application counts (not limited).
    Useful for "See all" functionality.
    
    Args:
        start_date: Start of current period
        end_date: End of current period
        period_days: Length of period
        company_id: Optional company ID to filter by
        
    Returns:
        List of all industries with metrics
    """
    result = calculate_top_industries(
        start_date=start_date,
        end_date=end_date,
        period_days=period_days,
        company_id=company_id,
        limit=1000  # Get all
    )
    return result.get("industries", [])
