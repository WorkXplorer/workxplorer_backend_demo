from django.core.management.base import BaseCommand
from apps.vacancies.services.expire_vacancy_task import expire_old_vacancies


class Command(BaseCommand):
    help = "Expire vacancies older than 30 days"

    def handle(self, *args, **options):
        self.stdout.write("Starting vacancy expiration process...")

        try:
            result = expire_old_vacancies()

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nExpiration complete!\n"
                    f"Total found: {result['total_found']}\n"
                    f"Expired: {result['expired']}\n"
                    f"Timestamp: {result['timestamp']}"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during expiration: {str(e)}"))
            raise
