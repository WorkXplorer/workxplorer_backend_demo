"""
Employed graduates analytics for EduPartner analytics data.
Handles the calculation of graduate employment statistics.
"""

import logging
from collections import defaultdict

from apps.resumes.models import Resume
from apps.resumes.models.choices import WorkStatus

logger = logging.getLogger(__name__)


def get_employed_graduates(candidate_ids: list, total_candidates: int) -> dict:
    """
    Calculate the number and percentage of employed graduates.
    Uses Resume.work_status to determine employment status.

    Args:
        candidate_ids: List of candidate IDs from the edupartner
        total_candidates: Total number of candidates from the edupartner

    Returns:
        dict: Employment statistics including count and percentage
    """
    if not candidate_ids or total_candidates == 0:
        return {
            "total_graduates": 0,
            "employed_count": 0,
            "employment_rate_percentage": 0,
            "by_status": {},
        }

    # Get work_status from active resumes of candidates
    # Use the most recent resume per candidate
    resume_stats = (
        Resume.objects.filter(candidate_id__in=candidate_ids, is_active=True)
        .order_by("candidate_id", "-created_at")
        .values("candidate_id", "work_status")
        .distinct("candidate_id")
    )

    # Count by status (we now have exactly one status per candidate - the latest)
    candidate_statuses = {}
    for item in resume_stats:
        candidate_id = item["candidate_id"]
        work_status = item["work_status"]
        candidate_statuses[candidate_id] = work_status

    # Count statuses
    by_status = defaultdict(int)
    for status in candidate_statuses.values():
        by_status[status] += 1

    # Count as "employed": EMPLOYED, SELF_EMPLOYED, FREELANCER
    employed_statuses = WorkStatus.employed_statuses()
    employed_count = sum(by_status.get(status, 0) for status in employed_statuses)

    # Calculate employment rate
    employment_rate = (
        (employed_count / total_candidates) * 100 if total_candidates > 0 else 0
    )

    return {
        "total_graduates": total_candidates,
        "employed_count": employed_count,
        "employment_rate_percentage": round(employment_rate, 1),
        "by_status": dict(by_status),
    }
