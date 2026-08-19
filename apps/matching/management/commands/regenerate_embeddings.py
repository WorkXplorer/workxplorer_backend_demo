from django.core.management.base import BaseCommand
from django_rq import enqueue

from apps.matching.services.embedding_tasks import (
    generate_resume_embedding_task,
    generate_vacancy_embedding_task,
)


class Command(BaseCommand):
    help = "Re-enqueue embedding generation for all resumes and/or vacancies"

    def add_arguments(self, parser):
        parser.add_argument(
            "--resumes",
            action="store_true",
            help="Regenerate embeddings for all resumes",
        )
        parser.add_argument(
            "--vacancies",
            action="store_true",
            help="Regenerate embeddings for all vacancies",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Regenerate embeddings for both resumes and vacancies",
        )

    def handle(self, *args, **options):
        do_resumes = options["resumes"] or options["all"]
        do_vacancies = options["vacancies"] or options["all"]

        if not do_resumes and not do_vacancies:
            self.stderr.write("Specify --resumes, --vacancies, or --all")
            return

        if do_resumes:
            from apps.resumes.models import Resume

            ids = list(Resume.objects.values_list("id", flat=True))
            for resume_id in ids:
                enqueue(generate_resume_embedding_task, resume_id)
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued {len(ids)} resume embedding tasks")
            )

        if do_vacancies:
            from apps.vacancies.models import Vacancy

            ids = list(Vacancy.objects.filter(is_active=True).values_list("id", flat=True))
            for vacancy_id in ids:
                enqueue(generate_vacancy_embedding_task, vacancy_id)
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued {len(ids)} vacancy embedding tasks")
            )
