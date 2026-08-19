import logging
from django.utils import timezone
from apps.vacancies.models import Vacancy

logger = logging.getLogger(__name__)


def expire_old_vacancies():
    """
    Find and expire all active vacancies that have exceeded their expiration period.
    Each vacancy can have a custom expiration period (expire field, default 30 days).
    This task should be run periodically (e.g., daily) via RQ scheduler.
    """
    logger.info("Starting vacancy expiration task...")

    now = timezone.now()

    # Get all active vacancies and check each one's custom expiration
    active_vacancies = Vacancy.objects.filter(is_active=True).only(
        "id", "title", "created_at", "expire", "is_active"
    )

    total_count = active_vacancies.count()
    expired_count = 0

    logger.info(f"Checking {total_count} active vacancies for expiration")

    for vacancy in active_vacancies:
        try:
            if vacancy.expire_vacancy():
                expired_count += 1
                logger.debug(f"Expired vacancy: {vacancy.id} - {vacancy.title}")
        except Exception as e:
            logger.error(f"Error expiring vacancy {vacancy.id}: {str(e)}")

    logger.info(
        f"Vacancy expiration complete. Expired {expired_count} out of {total_count} vacancies"
    )

    return {
        "total_found": total_count,
        "expired": expired_count,
        "timestamp": now.isoformat(),
    }
