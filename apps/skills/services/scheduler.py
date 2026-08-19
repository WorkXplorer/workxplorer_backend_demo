"""
RQ scheduler registration for the skills app.

Registers the daily passive-skill validation cron job. Mirrors the pattern in
``apps.general.services.scheduler`` — the module auto-schedules on import, which
happens from ``SkillsConfig.ready()``.
"""

import logging

from django.conf import settings
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler

from apps.skills.tasks import validate_passive_skills_task

logger = logging.getLogger(__name__)

REDIS_URL = getattr(settings, "REDIS_URL")
redis_conn = Redis.from_url(REDIS_URL)

q = Queue("default", connection=redis_conn)
scheduler = Scheduler(queue=q, connection=redis_conn)

SKILL_VALIDATION_JOB_ID = "validate_passive_skills_daily"

# Cron string is evaluated in UTC by rq-scheduler. Uzbekistan is a fixed UTC+5
# (no DST), so 22:00 UTC == 03:00 Asia/Tashkent. Overridable via settings.
SKILL_VALIDATION_CRON = getattr(settings, "SKILL_VALIDATION_CRON", "0 22 * * *")


def schedule_skill_validation(cron_string: str = SKILL_VALIDATION_CRON):
    """
    Register the daily passive-skill validation cron job (idempotent).

    Skips registration if a job with :data:`SKILL_VALIDATION_JOB_ID` already
    exists, so repeated imports across worker/web processes don't duplicate it.
    """
    try:
        for job in scheduler.get_jobs():
            if job.id == SKILL_VALIDATION_JOB_ID:
                logger.info(
                    "Passive skill validation already scheduled (job id=%s). Skipping.",
                    job.id,
                )
                return job

        job = scheduler.cron(
            cron_string=cron_string,
            func=validate_passive_skills_task,
            id=SKILL_VALIDATION_JOB_ID,
            timeout=1800,
            meta={"scheduled_by": "apps.skills.services.scheduler"},
        )
        logger.info(
            "Scheduled validate_passive_skills_task with cron '%s' (job id=%s).",
            cron_string,
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to schedule validate_passive_skills_task")
        raise


# Auto-schedule on import (mirrors apps.general.services.scheduler).
try:
    schedule_skill_validation()
except Exception:
    logger.warning("Failed to auto-schedule passive skill validation on import")
