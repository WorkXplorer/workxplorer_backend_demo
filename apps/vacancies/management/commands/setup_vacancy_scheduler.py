from django.core.management.base import BaseCommand
from django_rq import get_scheduler
from apps.vacancies.services.expire_vacancy_task import expire_old_vacancies


class Command(BaseCommand):
    help = "Set up recurring task to expire old vacancies daily at midnight"

    def handle(self, *args, **options):
        scheduler = get_scheduler("default")

        # Clear any existing jobs with this ID
        for job in scheduler.get_jobs():
            if job.id == "expire_old_vacancies_daily":
                scheduler.cancel(job)
                self.stdout.write("Removed existing scheduler job")

        # Schedule to run daily at midnight (00:00)
        # cron_string format: minute hour day month day_of_week
        scheduler.cron(
            cron_string="0 0 * * *",  # Every day at 00:00 (midnight)
            func=expire_old_vacancies,
            id="expire_old_vacancies_daily",
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Successfully scheduled vacancy expiration task to run daily at 00:00 (midnight)"
            )
        )
