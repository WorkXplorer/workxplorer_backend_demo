"""
Signals for the applications app.

This module contains signal handlers for:
- Automatically initializing company statuses when a new company is created
- Clearing status cache when statuses are modified
- Triggering AI candidate evaluation when a JobApplication is created
"""

import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


@receiver(post_save, sender='authentication.Company')
def initialize_company_statuses(sender, instance, created, **kwargs):
    """
    Initialize default statuses for a newly created company.
    """
    if not created:
        return

    from apps.applications.models import StatusTemplate, ApplicationStatusModel

    if ApplicationStatusModel.objects.filter(company=instance).exists():
        logger.info(f"Company {instance.name} already has statuses, skipping initialization")
        return

    template = StatusTemplate.objects.filter(is_default=True).first()

    if not template:
        logger.warning(
            f"No default status template found. Company {instance.name} "
            "will not have initial statuses configured."
        )
        return

    try:
        result = template.apply_to_company(instance)
        logger.info(
            f"Initialized {result['statuses_created']} statuses for company {instance.name}"
        )
    except Exception as e:
        logger.error(
            f"Failed to initialize statuses for company {instance.name}: {e}"
        )


@receiver([post_save, post_delete], sender='applications.ApplicationStatusModel')
def clear_status_cache_on_change(sender, instance, **kwargs):
    """
    Clear the status category cache when statuses are modified.
    """
    try:
        from apps.general.services.analytics.status_helpers import clear_status_cache
        clear_status_cache()
        logger.debug(f"Cleared status cache after change to {instance.key}")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Failed to clear status cache: {e}")


@receiver(post_save, sender='applications.JobApplication')
def trigger_candidate_ai_evaluation(sender, instance, created, **kwargs):
    """
    When a new JobApplication is saved, create an AIEvaluation record
    and enqueue the evaluation task via RQ.

    Uses transaction.on_commit so the RQ task only runs after the
    database transaction commits (ensuring the application row exists).
    """
    if not created:
        return

    try:
        from apps.applications.models import ApplicationAIEvaluation, EvaluationStatus
        from apps.general.models import JobQueue

        # Create the evaluation placeholder record
        evaluation, ev_created = ApplicationAIEvaluation.objects.get_or_create(
            application=instance,
            defaults={"status": EvaluationStatus.PENDING},
        )
        if not ev_created:
            return

        # Companies that are not yet approved get a static demo evaluation
        # instead of a real AI-generated one, so recruiters can preview
        # the feature before their company is verified.
        if getattr(instance, "is_demo", False) or not instance.vacancy.company.is_active:
            from apps.applications.services.demo_evaluation import DEMO_AI_EVALUATION_RESULT

            evaluation.status = EvaluationStatus.COMPLETED
            evaluation.result = DEMO_AI_EVALUATION_RESULT
            evaluation.overall_score = DEMO_AI_EVALUATION_RESULT["overall_score"]
            evaluation.detected_language = "uz"
            evaluation.evaluated_at = timezone.now()
            evaluation.save(
                update_fields=[
                    "status", "result", "overall_score", "detected_language",
                    "evaluated_at", "updated_at",
                ]
            )
            return

        # Create a JobQueue entry for tracking / retry
        candidate_name = str(instance.candidate)
        job = JobQueue.objects.create(
            job_type=JobQueue.JobType.CANDIDATE_EVALUATION,
            target_id=str(instance.id),
            target_date=timezone.now().date(),
            target_name=candidate_name,
            status=JobQueue.JobStatus.PENDING,
        )

        # Store the job queue id on the evaluation so the task can update it
        evaluation.job_queue_id = job.id
        evaluation.save(update_fields=["job_queue_id", "updated_at"])

        application_id = str(instance.id)
        job_queue_id = str(job.id)

        def _enqueue():
            try:
                import django_rq
                from apps.applications.tasks import process_candidate_ai_evaluation
                queue = django_rq.get_queue("default")
                queue.enqueue(
                    process_candidate_ai_evaluation,
                    application_id=application_id,
                    job_queue_id=job_queue_id,
                    retry_attempt=0,
                    job_timeout=300,
                )
                logger.info(
                    f"Enqueued AI evaluation for application {application_id}"
                )
            except Exception as enqueue_err:
                logger.error(
                    f"Failed to enqueue AI evaluation for application {application_id}: {enqueue_err}"
                )

        transaction.on_commit(_enqueue)

    except Exception as e:
        # Never crash application creation due to evaluation setup failures
        logger.error(
            f"Failed to set up AI evaluation for application {instance.id}: {e}",
            exc_info=True,
        )
