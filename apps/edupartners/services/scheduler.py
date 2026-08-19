import logging
from django.conf import settings
from datetime import datetime, timedelta, timezone
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler

from apps.edupartners.tasks import send_edupartner_analytics_data

logger = logging.getLogger(__name__)


REDIS_URL = getattr(settings, "REDIS_URL")
redis_conn = Redis.from_url(REDIS_URL)

# Queue and Scheduler
q = Queue("default", connection=redis_conn)
scheduler = Scheduler(queue=q, connection=redis_conn)

# 24 hours in seconds
EDUPARTNER_INTERVAL = settings.EDUPARTNER_INTERVAL if hasattr(settings, "EDUPARTNER_INTERVAL") else 86400  # Default to 24 hours


def _next_2am():
    """Calculate the next 02:00 AM datetime (UTC equivalent for Asia/Tashkent)."""
    now = datetime.now(timezone.utc)
    # Asia/Tashkent is UTC+5, so 02:00 local = 21:00 UTC previous day
    target_utc = now.replace(hour=21, minute=0, second=0, microsecond=0)
    if target_utc <= now:
        target_utc += timedelta(days=1)
    return target_utc


def schedule_edupartner_analytics(interval_seconds: int = EDUPARTNER_INTERVAL):
    """
    Schedule send_edupartner_analytics_data to run once per day at 02:00 AM.
    Uses a 24-hour interval starting from the next 02:00 AM.
    This master task will create individual jobs for each faculty.
    Avoids creating duplicate scheduled jobs by checking existing jobs.

    Args:
        interval_seconds: Interval in seconds between task executions (default: 86400 = 24h)

    Returns:
        Scheduled job instance or None
    """
    try:
        # Check for existing scheduled job
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or str(getattr(job, "func", ""))
            if "send_edupartner_analytics_data" in func_name:
                existing_interval = getattr(job, "interval", None)
                if existing_interval == interval_seconds:
                    logger.info(
                        "send_edupartner_analytics_data already scheduled (job id=%s). Skipping.",
                        job.id,
                    )
                    return job

                # Stale scheduler entry (e.g. old interval=60): recreate with current settings.
                scheduler.cancel(job)
                logger.info(
                    "Rescheduling send_edupartner_analytics_data due to interval change "
                    "(job id=%s, old_interval=%s, new_interval=%s).",
                    job.id,
                    existing_interval,
                    interval_seconds,
                )
                break

        # Schedule new job - starts at next 02:00 AM, repeats every 24 hours
        job = scheduler.schedule(
            scheduled_time=_next_2am(),
            func=send_edupartner_analytics_data,
            interval=interval_seconds,
            repeat=None,  # repeat forever
            meta={"scheduled_by": "apps.edupartners.services.scheduler"},
        )

        logger.info(
            "Scheduled send_edupartner_analytics_data every %s seconds (job id=%s). "
            "Each run will create individual jobs per faculty.",
            interval_seconds,
            job.id,
        )
        return job

    except Exception:
        logger.exception("Failed to schedule send_edupartner_analytics_data")
        raise


def cancel_edupartner_analytics_schedule():
    """
    Cancel all scheduled edupartner analytics jobs.
    Useful for maintenance or reconfiguration.
    """
    try:
        cancelled_count = 0
        for job in scheduler.get_jobs():
            func_name = getattr(job, "func_name", "") or str(getattr(job, "func", ""))
            if "send_edupartner_analytics_data" in func_name:
                scheduler.cancel(job)
                cancelled_count += 1
                logger.info(f"Cancelled scheduled job: {job.id}")

        logger.info(f"Cancelled {cancelled_count} scheduled analytics jobs")
        return cancelled_count
    except Exception:
        logger.exception("Failed to cancel scheduled jobs")
        raise


# Auto-schedule on import (only in production/staging)
if not getattr(settings, "TESTING", False):
    try:
        schedule_edupartner_analytics(EDUPARTNER_INTERVAL)
    except Exception:
        # Scheduling failure is logged above
        pass
