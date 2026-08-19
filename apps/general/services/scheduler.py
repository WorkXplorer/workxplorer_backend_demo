import logging
from django.conf import settings
from datetime import datetime, timedelta, timezone
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler

# Import the clean tasks.py pattern (like EduPartner)
from apps.general.tasks import (
    send_hr_analytics_data,
    send_vacancy_analytics_data,
    send_recruiter_applications_summary,
    sync_hh_market_skills,
    sync_stat_uz_sector_salaries,
    classify_domain_sectors_task,
)
from apps.general.currency.fetcher import update_all_currency_rates

logger = logging.getLogger(__name__)


REDIS_URL = getattr(settings, "REDIS_URL")
redis_conn = Redis.from_url(REDIS_URL)

# Queue and Scheduler
q = Queue("default", connection=redis_conn)
scheduler = Scheduler(queue=q, connection=redis_conn)

# Default interval for HR analytics (in seconds) - can be overridden in settings
HR_ANALYTICS_INTERVAL = settings.HR_ANALYTICS_INTERVAL if hasattr(settings, "HR_ANALYTICS_INTERVAL") else 14400  # Default to 4 hours
HH_MARKET_SYNC_INTERVAL = getattr(settings, "HH_MARKET_SYNC_INTERVAL_SECONDS", 60 * 24 * 60 * 60)
STAT_UZ_SECTOR_SALARY_SYNC_INTERVAL = getattr(
    settings, "STAT_UZ_SECTOR_SALARY_SYNC_INTERVAL_SECONDS", 7 * 24 * 60 * 60
)


def schedule_hr_analytics(interval_seconds: int = HR_ANALYTICS_INTERVAL):
    """
    Schedule HR analytics collection to run every `interval_seconds`.
    Uses the tasks.py structure similar to EduPartner.
    Default: every 4 hours (14400 seconds).
    
    This is the ONLY scheduler function - there is no duplicate.
    """
    try:
        # Check for existing scheduled job
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "send_hr_analytics_data" in func_name:
                logger.info(
                    "send_hr_analytics_data already scheduled (job id=%s). Skipping.", job.id
                )
                return job

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),
            func=send_hr_analytics_data,
            interval=interval_seconds,
            repeat=None,  # repeat forever
            meta={"scheduled_by": "apps.general.tasks"},
        )
        logger.info(
            "Scheduled send_hr_analytics_data every %s seconds (job id=%s).",
            interval_seconds,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule send_hr_analytics_data")
        raise


def schedule_vacancy_analytics(interval_seconds: int = HR_ANALYTICS_INTERVAL):
    """
    Schedule vacancy analytics collection to run every `interval_seconds`.
    Vacancy data is sent to a dedicated webhook endpoint, separate from company analytics.
    Default: every 4 hours (same cadence as company analytics).
    """
    try:
        # Check for existing scheduled job
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "send_vacancy_analytics_data" in func_name:
                logger.info(
                    "send_vacancy_analytics_data already scheduled (job id=%s). Skipping.", job.id
                )
                return job

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),
            func=send_vacancy_analytics_data,
            interval=interval_seconds,
            repeat=None,  # repeat forever
            meta={"scheduled_by": "apps.general.tasks"},
        )
        logger.info(
            "Scheduled send_vacancy_analytics_data every %s seconds (job id=%s).",
            interval_seconds,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule send_vacancy_analytics_data")
        raise


def schedule_currency_update():
    """
    Schedule daily currency rate update at 02:00 AM (Asia/Tashkent).
    Fetches USD, RUB, EUR rates from CBU API and saves as JSON.
    """
    try:
        # Check for existing scheduled job
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "update_all_currency_rates" in func_name:
                logger.info(
                    "update_all_currency_rates already scheduled (job id=%s). Skipping.", job.id
                )
                return job

        # Schedule to run daily (every 24 hours)
        job = scheduler.schedule(
            scheduled_time=_next_2am(),
            func=update_all_currency_rates,
            interval=86400,  # 24 hours
            repeat=None,  # repeat forever
            meta={"scheduled_by": "apps.general.services.scheduler"},
        )
        logger.info(
            "Scheduled update_all_currency_rates daily at 02:00 AM (job id=%s).",
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule update_all_currency_rates")
        raise


def _next_2am():
    """Calculate the next 02:00 AM datetime."""
    now = datetime.now(timezone.utc)
    # Asia/Tashkent is UTC+5, so 02:00 local = 21:00 UTC previous day
    target_utc = now.replace(hour=21, minute=0, second=0, microsecond=0)
    if target_utc <= now:
        target_utc += timedelta(days=1)
    return target_utc


def schedule_recruiter_applications_summary(interval_seconds: int = HR_ANALYTICS_INTERVAL):
    """
    Schedule recruiter applications summary emails to run every `interval_seconds`.
    Sends recruiters a digest of new candidate applications from the last 4 hours.
    Default: every 4 hours (14400 seconds).
    """
    try:
        # Check for existing scheduled job
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "send_recruiter_applications_summary" in func_name:
                logger.info(
                    "send_recruiter_applications_summary already scheduled (job id=%s). Skipping.", job.id
                )
                return job

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),
            func=send_recruiter_applications_summary,
            interval=interval_seconds,
            repeat=None,  # repeat forever
            meta={"scheduled_by": "apps.general.services.scheduler"},
        )
        logger.info(
            "Scheduled send_recruiter_applications_summary every %s seconds (job id=%s).",
            interval_seconds,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule send_recruiter_applications_summary")
        raise


def schedule_hh_market_skills(interval_seconds: int = HH_MARKET_SYNC_INTERVAL):
    """
    Schedule HH market skills to refresh every two months by default.
    """
    try:
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "sync_hh_market_skills" in func_name:
                logger.info(
                    "HH market skills sync already scheduled (job id=%s). Skipping.",
                    job.id,
                )
                return job

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),
            func=sync_hh_market_skills,
            interval=interval_seconds,
            repeat=None,
            meta={"scheduled_by": "apps.general.services.scheduler"},
        )
        logger.info(
            "Scheduled sync_hh_market_skills every %s seconds (job id=%s).",
            interval_seconds,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule sync_hh_market_skills")
        raise


def schedule_stat_uz_sector_salary_sync(interval_seconds: int = STAT_UZ_SECTOR_SALARY_SYNC_INTERVAL):
    """
    Schedule the stat.uz sector salary refresh weekly. The underlying data
    is published quarterly, but polling weekly picks up a new quarter
    promptly at negligible cost (the whole table is under a thousand rows).
    """
    try:
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "sync_stat_uz_sector_salaries" in func_name:
                logger.info(
                    "stat.uz sector salary sync already scheduled (job id=%s). Skipping.",
                    job.id,
                )
                return job

        job = scheduler.schedule(
            scheduled_time=datetime.now(timezone.utc),
            func=sync_stat_uz_sector_salaries,
            interval=interval_seconds,
            repeat=None,
            meta={"scheduled_by": "apps.general.services.scheduler"},
        )
        logger.info(
            "Scheduled sync_stat_uz_sector_salaries every %s seconds (job id=%s).",
            interval_seconds,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule sync_stat_uz_sector_salaries")
        raise


def schedule_domain_sector_classification():
    """
    Schedule the Domain -> stat.uz sector_code classification pass on the
    1st of every month at 00:00 UTC. Also runnable manually via
    `manage.py classify_domain_sectors`.
    """
    try:
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or getattr(job, "func", None)
            if isinstance(func_name, str) and "classify_domain_sectors_task" in func_name:
                logger.info(
                    "Domain sector classification already scheduled (job id=%s). Skipping.",
                    job.id,
                )
                return job

        job = scheduler.cron(
            "0 0 1 * *",
            func=classify_domain_sectors_task,
            repeat=None,
            meta={"scheduled_by": "apps.general.services.scheduler"},
        )
        logger.info(
            "Scheduled classify_domain_sectors_task for the 1st of every month (job id=%s).",
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule classify_domain_sectors_task")
        raise


# Auto-schedule on import
try:
    schedule_hr_analytics()
except Exception:
    logger.warning("Failed to auto-schedule HR analytics on import")

try:
    schedule_vacancy_analytics()
except Exception:
    logger.warning("Failed to auto-schedule vacancy analytics on import")

try:
    schedule_currency_update()  # Daily at 02:00 AM
except Exception:
    logger.warning("Failed to auto-schedule currency update on import")

try:
    schedule_recruiter_applications_summary()  # Every 4 hours
except Exception:
    logger.warning("Failed to auto-schedule recruiter applications summary on import")

try:
    schedule_hh_market_skills()  # Every 60 days
except Exception:
    logger.warning("Failed to auto-schedule HH market skills on import")

try:
    schedule_stat_uz_sector_salary_sync()  # Weekly
except Exception:
    logger.warning("Failed to auto-schedule stat.uz sector salary sync on import")

try:
    schedule_domain_sector_classification()  # Monthly, 1st at 00:00 UTC
except Exception:
    logger.warning("Failed to auto-schedule domain sector classification on import")
