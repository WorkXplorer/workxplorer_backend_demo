"""
Experience calculation utilities for resumes.

Provides accurate experience calculation based on start_date/end_date,
with support for overlapping work periods (no double-counting).
Uses ngettext for proper pluralization in uz, ru, en.
"""

from datetime import date
from typing import List, Tuple, Optional

from django.utils.translation import ngettext


def calculate_total_experience_months(
    intervals: List[Tuple[date, Optional[date]]],
) -> int:
    """
    Calculate total experience in months from a list of (start_date, end_date) intervals.

    Handles overlapping periods by merging intervals so overlapping months
    are only counted once.

    If end_date is None, assumes the candidate is still working there
    and uses today's date.

    Args:
        intervals: List of (start_date, end_date) tuples.

    Returns:
        Total unique months of experience.
    """
    if not intervals:
        return 0

    today = date.today()

    # Normalize: replace None end_date with today, convert to (start, end) month tuples
    month_intervals = []
    for start, end in intervals:
        if start is None:
            continue
        end = end or today
        if end < start:
            continue
        # Convert to month-based integers for merging
        # Use exclusive end: +1 ensures single-month periods count as 1, not 0
        start_month = start.year * 12 + start.month
        end_month = end.year * 12 + end.month + 1
        month_intervals.append((start_month, end_month))

    if not month_intervals:
        return 0

    # Sort by start month
    month_intervals.sort()

    # Merge overlapping intervals
    merged = [month_intervals[0]]
    for current_start, current_end in month_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if current_start <= prev_end:
            # Overlapping or adjacent — merge
            merged[-1] = (prev_start, max(prev_end, current_end))
        else:
            merged.append((current_start, current_end))

    # Sum the total months from merged intervals
    total_months = sum(end - start for start, end in merged)
    return max(total_months, 0)


def format_experience(total_months: int) -> str:
    """
    Format total months as a human-readable, localized string.

    Uses ngettext for proper plural forms across languages (uz, ru, en).
    Russian requires 3 plural forms (год/года/лет, месяц/месяца/месяцев).

    Examples (en):
        0  -> "0 months"
        1  -> "1 month"
        5  -> "5 months"
        12 -> "1 year"
        13 -> "1 year 1 month"
        20 -> "1 year 8 months"
        24 -> "2 years"
        25 -> "2 years 1 month"

    Args:
        total_months: Total experience in months.

    Returns:
        Localized formatted string.
    """
    if total_months <= 0:
        # Translators: experience duration when 0 months
        return ngettext(
            "%(count)d month",
            "%(count)d months",
            0,
        ) % {"count": 0}

    years, months = divmod(total_months, 12)

    parts = []
    if years > 0:
        # Translators: number of years of experience
        parts.append(
            ngettext(
                "%(count)d year",
                "%(count)d years",
                years,
            ) % {"count": years}
        )

    if months > 0:
        # Translators: number of months of experience
        parts.append(
            ngettext(
                "%(count)d month",
                "%(count)d months",
                months,
            ) % {"count": months}
        )

    return " ".join(parts) if parts else ngettext(
        "%(count)d month",
        "%(count)d months",
        0,
    ) % {"count": 0}
