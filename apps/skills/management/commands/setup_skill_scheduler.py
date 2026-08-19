"""
Management command to (re)register the daily passive-skill validation cron job.

Cancels any existing job with the same id and schedules it fresh, so it can be
used to apply a changed cron string. Run once after deploy, e.g.:

    python manage.py setup_skill_scheduler
"""

from django.core.management.base import BaseCommand

from apps.skills.services.scheduler import (
    SKILL_VALIDATION_CRON,
    SKILL_VALIDATION_JOB_ID,
    schedule_skill_validation,
    scheduler,
)


class Command(BaseCommand):
    help = "Schedule the daily passive-skill AI validation job (03:00 Asia/Tashkent)."

    def handle(self, *args, **options):
        for job in scheduler.get_jobs():
            if job.id == SKILL_VALIDATION_JOB_ID:
                scheduler.cancel(job)
                self.stdout.write("Removed existing skill validation job.")

        job = schedule_skill_validation()

        self.stdout.write(
            self.style.SUCCESS(
                "Scheduled passive-skill validation (job id=%s, cron='%s', "
                "03:00 Asia/Tashkent)." % (job.id, SKILL_VALIDATION_CRON)
            )
        )
