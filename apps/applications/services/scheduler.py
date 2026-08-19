"""
RQ scheduler registration for the applications app.

Registers the daily application report cron job. Mirrors the pattern in
``apps.skills.services.scheduler`` — the module auto-schedules on import, which
happens from ``ApplicationsConfig.ready()``.
"""

import logging

from django.conf import settings
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler

from apps.applications.tasks import send_daily_application_report_task

logger = logging.getLogger(__name__)

REDIS_URL = getattr(settings, "REDIS_URL")
redis_conn = Redis.from_url(REDIS_URL)

q = Queue("default", connection=redis_conn)
scheduler = Scheduler(queue=q, connection=redis_conn)

DAILY_APPLICATION_REPORT_JOB_ID = "send_daily_application_report"

# Cron string is evaluated in UTC by rq-scheduler. Uzbekistan is a fixed UTC+5
# (no DST), so 04:00 UTC == 09:00 Asia/Tashkent. Overridable via settings.
DAILY_APPLICATION_REPORT_CRON = getattr(
    settings, "DAILY_APPLICATION_REPORT_CRON", "0 4 * * *"
)


def schedule_daily_application_report(
    cron_string: str = DAILY_APPLICATION_REPORT_CRON,
):
    """
    Register the daily application report cron job (idempotent).

    Skips registration if a job with :data:`DAILY_APPLICATION_REPORT_JOB_ID`
    already exists, so repeated imports across worker/web processes don't
    duplicate it.
    """
    try:
        for job in scheduler.get_jobs():
            if job.id == DAILY_APPLICATION_REPORT_JOB_ID:
                logger.info(
                    "Daily application report already scheduled (job id=%s). Skipping.",
                    job.id,
                )
                return job

        job = scheduler.cron(
            cron_string=cron_string,
            func=send_daily_application_report_task,
            id=DAILY_APPLICATION_REPORT_JOB_ID,
            timeout=600,
            meta={"scheduled_by": "apps.applications.services.scheduler"},
        )
        logger.info(
            "Scheduled send_daily_application_report_task with cron '%s' (job id=%s).",
            cron_string,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule send_daily_application_report_task")
        raise


if getattr(settings, "DAILY_APPLICATION_REPORT_ENABLED", True):
    # Auto-schedule on import (mirrors apps.skills.services.scheduler).
    try:
        schedule_daily_application_report()
    except Exception:
        logger.warning("Failed to auto-schedule daily application report on import")
