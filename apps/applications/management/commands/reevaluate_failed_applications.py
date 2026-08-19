"""
Management command to re-enqueue AI evaluations that failed (e.g. due to a
transient AI provider API error).

For each FAILED ApplicationAIEvaluation:
  1. Resets evaluation status → PENDING and clears error_message.
  2. Resets the linked JobQueue entry → PENDING with retry_count=0
     so the task's retry guard lets it run again.
  3. Re-enqueues process_candidate_ai_evaluation on the default RQ queue.

With --force, also re-enqueues evaluations that already succeeded
(e.g. after adding cover_letter to the AI context).

Usage:
    python manage.py reevaluate_failed_applications
    python manage.py reevaluate_failed_applications --dry-run
    python manage.py reevaluate_failed_applications --email=user@example.com
    python manage.py reevaluate_failed_applications --application-id=<UUID>
    python manage.py reevaluate_failed_applications --force --application-id=<UUID>
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Re-enqueue failed AI evaluations for re-processing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be re-enqueued without making any changes",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Filter by candidate email address",
        )
        parser.add_argument(
            "--application-id",
            type=str,
            help="Re-evaluate a specific application by UUID",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-enqueue even if evaluation already succeeded (e.g. after adding cover_letter to context)",
        )

    def handle(self, *args, **options):
        from apps.applications.models import ApplicationAIEvaluation, EvaluationStatus
        from apps.general.models import JobQueue

        dry_run = options["dry_run"]
        email_filter = options.get("email")
        app_id_filter = options.get("application_id")
        force = options["force"]

        base_qs = ApplicationAIEvaluation.objects.select_related(
            "application",
            "application__candidate",
            "application__vacancy",
        )

        if force:
            queryset = base_qs.all()
        else:
            queryset = base_qs.filter(status=EvaluationStatus.FAILED)

        if app_id_filter:
            queryset = queryset.filter(application_id=app_id_filter)

        if email_filter:
            queryset = queryset.filter(
                application__candidate__email=email_filter,
            )

        total = queryset.count()
        label = "evaluation(s)" if force else "failed evaluation(s)"
        self.stdout.write(f"Found {total} {label} to re-enqueue.\n")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        enqueued = 0
        skipped = 0

        for evaluation in queryset:
            application = evaluation.application
            candidate = application.candidate
            vacancy = application.vacancy
            label = (
                f"application {application.id} "
                f"({getattr(candidate, 'email', '?')} → {vacancy.title})"
            )

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] Would re-enqueue {label}\n"
                    f"            Error was: {evaluation.error_message or '(none)'}"
                )
                enqueued += 1
                continue

            try:
                with transaction.atomic():
                    # 1. Reset evaluation to PENDING
                    evaluation.status = EvaluationStatus.PENDING
                    evaluation.error_message = None
                    evaluation.save(update_fields=["status", "error_message", "updated_at"])

                    # 2. Reset linked JobQueue so the retry guard allows execution
                    if evaluation.job_queue_id:
                        JobQueue.objects.filter(id=evaluation.job_queue_id).update(
                            status=JobQueue.JobStatus.PENDING,
                            retry_count=0,
                            error_message=None,
                        )
                        job_queue_id = str(evaluation.job_queue_id)
                    else:
                        job_queue_id = None

                # 3. Re-enqueue outside the transaction so the task sees the
                #    committed PENDING state when it acquires the row lock.
                import django_rq
                from apps.applications.tasks import process_candidate_ai_evaluation

                queue = django_rq.get_queue("default")
                queue.enqueue(
                    process_candidate_ai_evaluation,
                    application_id=str(application.id),
                    job_queue_id=job_queue_id,
                    retry_attempt=0,
                    job_timeout=300,
                )

                self.stdout.write(self.style.SUCCESS(f"  Re-enqueued {label}"))
                enqueued += 1

            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"  FAILED to re-enqueue {label}: {exc}")
                )
                logger.exception(f"reevaluate_failed_applications: error re-enqueuing {application.id}")
                skipped += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDry run complete. {enqueued} would be re-enqueued.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nDone. {enqueued} re-enqueued, {skipped} skipped due to errors.")
            )
