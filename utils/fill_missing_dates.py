"""
Utility functions for filling missing dates in time-series data.
Used primarily for analytics data to ensure complete date ranges.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any

from django.utils import timezone


def fill_daily_data(
        industries: List[Dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
        domain_ids: List[str] = None,
        domain_names: Dict[str, str] = None,
) -> List[Dict[str, Any]]:
    """
    Fill missing daily dates for industry data.
    
    If industries is empty but domain_ids are provided, creates entries
    for each domain with all dates filled with zeros.
    
    Args:
        industries: List of industry data dictionaries
        start_date: Start date of the range
        end_date: End date of the range
        domain_ids: Optional list of domain IDs to create entries for if industries is empty
        domain_names: Optional dict mapping domain_id to domain_name
        
    Returns:
        list: Industries with complete daily data
    """
    # Generate all dates in the range
    all_dates = _generate_date_range(start_date, end_date)

    # If no industries data but domain_ids provided, create empty structure
    if not industries and domain_ids:
        industries = [
            {
                "domain_id": str(did),
                "domain_name": domain_names.get(str(did), "") if domain_names else "",
                "daily_data": [],
            }
            for did in domain_ids
        ]

    if not industries:
        return []

    result = []
    for industry in industries:
        domain_id = industry.get("domain_id", "")
        domain_name = industry.get("domain_name", "")
        existing_data = industry.get("daily_data", [])

        # Create a map of existing dates to positions
        existing_map = _build_daily_map(existing_data)

        # Build complete daily data
        filled_data = []
        for date in all_dates:
            date_key = date.strftime("%Y-%m-%d")
            date_iso = date.isoformat()

            positions = existing_map.get(date_key, 0)
            filled_data.append({
                "date": date_iso,
                "positions": positions,
            })

        result.append({
            "domain_id": domain_id,
            "domain_name": domain_name,
            "daily_data": filled_data,
        })

    return result


def fill_monthly_data(
        industries: List[Dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
        domain_ids: List[str] = None,
        domain_names: Dict[str, str] = None,
) -> List[Dict[str, Any]]:
    """
    Fill missing monthly dates for industry data.
    
    If industries is empty but domain_ids are provided, creates entries
    for each domain with all months filled with zeros.
    
    Args:
        industries: List of industry data dictionaries
        start_date: Start date of the range
        end_date: End date of the range
        domain_ids: Optional list of domain IDs to create entries for if industries is empty
        domain_names: Optional dict mapping domain_id to domain_name
        
    Returns:
        list: Industries with complete monthly data
    """
    # Generate all months in the range
    all_months = _generate_month_range(start_date, end_date)

    # If no industries data but domain_ids provided, create empty structure
    if not industries and domain_ids:
        industries = [
            {
                "domain_id": str(did),
                "domain_name": domain_names.get(str(did), "") if domain_names else "",
                "monthly_data": [],
            }
            for did in domain_ids
        ]

    if not industries:
        return []

    result = []
    for industry in industries:
        domain_id = industry.get("domain_id", "")
        domain_name = industry.get("domain_name", "")
        existing_data = industry.get("monthly_data", [])

        # Create a map of existing months to positions
        existing_map = _build_monthly_map(existing_data)

        # Build complete monthly data
        filled_data = []
        for month_date in all_months:
            month_key = month_date.strftime("%Y-%m")
            month_name = month_date.strftime("%b")

            if month_key in existing_map:
                positions = existing_map[month_key]["positions"]
                # Use existing month_name if available, otherwise generate
                month_name = existing_map[month_key].get("month_name") or month_name
            else:
                positions = 0

            filled_data.append({
                "month": month_key,
                "month_name": month_name,
                "positions": positions,
            })

        result.append({
            "domain_id": domain_id,
            "domain_name": domain_name,
            "monthly_data": filled_data,
        })

    return result


def _generate_date_range(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Generate a list of all dates between start_date and end_date (inclusive).
    
    Args:
        start_date: Start date of the range
        end_date: End date of the range
        
    Returns:
        list: List of datetime objects for each day in the range
    """
    all_dates = []
    current = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    while current <= end:
        all_dates.append(current)
        current += timedelta(days=1)

    return all_dates


def _generate_month_range(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Generate a list of all months between start_date and end_date (inclusive).
    
    Args:
        start_date: Start date of the range
        end_date: End date of the range
        
    Returns:
        list: List of datetime objects for the first day of each month in the range
    """
    all_months = []
    current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    while current <= end:
        all_months.append(current)
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return all_months


def _build_daily_map(existing_data: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Build a map of date strings to positions from existing daily data.
    
    Args:
        existing_data: List of daily data dictionaries with 'date' and 'positions' keys
        
    Returns:
        dict: Map of date string (YYYY-MM-DD) to positions count
    """
    existing_map = {}
    for item in existing_data:
        date_str = item.get("date", "")
        # Handle both ISO format with timezone and simple date format
        try:
            if "T" in date_str:
                # Parse ISO format: "2025-12-09T00:00:00+05:00"
                parsed_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                date_key = parsed_date.strftime("%Y-%m-%d")
            else:
                date_key = date_str[:10] if len(date_str) >= 10 else date_str
        except (ValueError, TypeError):
            continue
        existing_map[date_key] = item.get("positions", 0)

    return existing_map


def _build_monthly_map(existing_data: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build a map of month strings to positions and month_name from existing monthly data.
    
    Args:
        existing_data: List of monthly data dictionaries with 'month', 'month_name', and 'positions' keys
        
    Returns:
        dict: Map of month string (YYYY-MM) to dict with 'positions' and 'month_name'
    """
    existing_map = {}
    for item in existing_data:
        month_str = item.get("month", "")  # Format: "2025-12"
        existing_map[month_str] = {
            "positions": item.get("positions", 0),
            "month_name": item.get("month_name", ""),
        }

    return existing_map


def get_current_month_range() -> tuple:
    """
    Get the start and end dates for the current month.
    
    Returns:
        tuple: (start_date, end_date) for the current month
    """
    now = timezone.now()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_date = now
    return start_date, end_date


def get_current_year_range() -> tuple:
    """
    Get the start and end dates for the current year (January to current month).
    
    Returns:
        tuple: (start_date, end_date) for the current year
    """
    now = timezone.now()
    start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    end_date = now
    return start_date, end_date


def get_last_7_days_range() -> tuple:
    """
    Get the start and end dates for the last 7 days (including today).
    
    Returns:
        tuple: (start_date, end_date) for the last 7 days
    """
    now = timezone.now()
    start_date = now - timedelta(days=6)  # 6 days ago + today = 7 days
    end_date = now
    return start_date, end_date
