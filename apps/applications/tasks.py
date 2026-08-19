"""
RQ Tasks for candidate AI evaluation.

Follows the same pattern as resumes/tasks.py.
Fires when a JobApplication is created (via signal) and evaluates the
candidate against the vacancy using the AI provider.
"""

import logging
import uuid
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

import django_rq

logger = logging.getLogger(__name__)


class CandidateEvaluationTaskError(Exception):
    """Custom exception for candidate evaluation task errors."""
    pass


def process_candidate_ai_evaluation(
    application_id: str,
    job_queue_id: Optional[str] = None,
    retry_attempt: int = 0,
) -> dict:
    """
    RQ task to evaluate a candidate against a vacancy using the AI provider.

    Steps:
    1. Load the JobApplication with related vacancy, candidate, and resume.
    2. Update ApplicationAIEvaluation status to PROCESSING.
    3. Detect language from candidate's preferred_language.
    4. Call the AI evaluation service to build context and call the AI provider.
    5. Store the JSON result, overall_score, language, and token usage on the evaluation record.
    6. If overall_score < vacancy.minimum_ai_score, auto-reject the application with conversation message and notification.
    7. Update JobQueue status to completed.

    Args:
        application_id: UUID of the JobApplication to evaluate.
        job_queue_id: UUID of the JobQueue entry for status tracking.
        retry_attempt: Current retry attempt number.

    Returns:
        Dict with success, data, and error keys.
    """
    from apps.general.services.job_queue_service import JobQueueService
    from apps.applications.models import ApplicationAIEvaluation, EvaluationStatus
    from apps.applications.services.ai_evaluation_service import evaluate_candidate_for_vacancy

    task_id = str(uuid.uuid4())[:8]
    logger.info(f"[EvalTask {task_id}] Starting AI evaluation for application {application_id}")

    # Load evaluation record with row lock to prevent duplicate processing
    try:
        with transaction.atomic():
            evaluation = ApplicationAIEvaluation.objects.select_related(
                "application",
                "application__vacancy",
                "application__vacancy__company",
                "application__candidate",
            ).select_for_update().get(application_id=application_id)

            if evaluation.status != EvaluationStatus.PENDING:
                logger.info(
                    f"[EvalTask {task_id}] Evaluation {application_id} already {evaluation.status}, skipping"
                )
                return {"success": False, "data": None, "error": f"Evaluation already {evaluation.status}"}

            # Mark as processing
            evaluation.status = EvaluationStatus.PROCESSING
            if job_queue_id:
                try:
                    evaluation.job_queue_id = uuid.UUID(job_queue_id)
                except (ValueError, AttributeError):
                    logger.warning(
                        f"[EvalTask {task_id}] Invalid job_queue_id '{job_queue_id}' for application "
                        f"{application_id}; proceeding without queue linkage."
                    )
            evaluation.save(update_fields=["status", "job_queue_id", "updated_at"])
    except ApplicationAIEvaluation.DoesNotExist:
        logger.error(f"[EvalTask {task_id}] No AIEvaluation record for application {application_id}")
        return {"success": False, "data": None, "error": "Evaluation record not found"}

    if job_queue_id:
        JobQueueService.update_job_status(job_queue_id, "processing")

    try:
        application = evaluation.application
        candidate = application.candidate

        # Detect language from candidate's preferred language
        detected_language = getattr(candidate, "preferred_language", "uz") or "uz"
        if detected_language not in ("uz", "ru", "en"):
            detected_language = "uz"

        # Run AI evaluation with language instruction
        logger.info(
            f"[EvalTask {task_id}] Calling AI provider for application {application_id} "
            f"(language={detected_language})"
        )
        output = evaluate_candidate_for_vacancy(application, language=detected_language)
        result = output["evaluation"]
        usage = output.get("usage", {})

        # Extract overall score
        overall_score = result.get("overall_score")
        if overall_score is not None:
            try:
                overall_score = float(overall_score)
            except (TypeError, ValueError):
                overall_score = None

        # Store result with language and token info
        application_status_at_evaluation = application.status
        evaluation.status = EvaluationStatus.COMPLETED
        evaluation.result = result
        evaluation.overall_score = overall_score
        evaluation.detected_language = detected_language
        evaluation.input_tokens = usage.get("prompt_tokens")
        evaluation.output_tokens = usage.get("completion_tokens")
        evaluation.thinking_tokens = usage.get("thinking_tokens")
        evaluation.evaluated_at = timezone.now()
        evaluation.error_message = None
        evaluation.save(update_fields=[
            "status", "result", "overall_score", "detected_language",
            "input_tokens", "output_tokens", "thinking_tokens", "evaluated_at",
            "error_message", "updated_at",
        ])

        # Auto-reject if overall_score is below the vacancy's threshold
        min_score = application.vacancy.minimum_ai_score
        if overall_score is not None and overall_score < min_score:
            logger.info(
                f"[EvalTask {task_id}] Score {overall_score} < {min_score}, auto-rejecting application "
                f"{application_id}"
            )
            _auto_reject_application(application, overall_score, application_status_at_evaluation)

        # Update job queue
        if job_queue_id:
            JobQueueService.update_job_status(job_queue_id, "completed")

        logger.info(
            f"[EvalTask {task_id}] Evaluation completed for application {application_id}. "
            f"Score: {overall_score}"
        )

        return {
            "success": True,
            "data": {
                "application_id": application_id,
                "overall_score": overall_score,
                "recommendation": result.get("recommendation"),
                "detected_language": detected_language,
            },
            "error": None,
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"[EvalTask {task_id}] Evaluation failed for application {application_id}: {e}")

        evaluation.status = EvaluationStatus.FAILED
        evaluation.error_message = error_msg
        evaluation.save(update_fields=["status", "error_message", "updated_at"])

        _handle_task_failure(
            job_queue_id=job_queue_id,
            error_message=error_msg,
            application_id=application_id,
            retry_attempt=retry_attempt,
        )

        return {
            "success": False,
            "data": None,
            "error": error_msg,
        }


def _auto_reject_application(application, overall_score: float, original_status: str = None):
    """
    Auto-reject an application when AI evaluation score is below the vacancy's minimum_ai_score threshold.

    Uses the company's flexible ApplicationStatusModel to find the AI_FAILED status,
    creates a conversation message, and sends a notification to the candidate.
    Uses select_for_update to prevent race conditions with concurrent status updates.

    Args:
        application: JobApplication instance
        overall_score: The AI evaluation score that triggered the auto-reject
        original_status: The application status at the time of evaluation (for TOCTOU guard)
    """
    from django.db import transaction as db_transaction
    from apps.applications.models import ApplicationStatusModel, StatusCategory, JobApplication
    from apps.conversations.services import create_status_change_message
    from apps.notifications.services import ApplicationNotificationService

    with db_transaction.atomic():
        locked_app = JobApplication.objects.select_for_update().get(pk=application.pk)

        # TOCTOU guard: check if status changed since evaluation completed
        if original_status is not None and locked_app.status != original_status:
            logger.info(
                f"Application {locked_app.id} status changed from {original_status} "
                f"to {locked_app.status} during evaluation — skipping auto-reject"
            )
            return

        ai_failed_status = ApplicationStatusModel.objects.filter(
            company=locked_app.vacancy.company,
            category__key=StatusCategory.AI_FAILED,
            is_active=True,
        ).first()

        if not ai_failed_status:
            logger.warning(
                f"No AI_FAILED ApplicationStatusModel found for company "
                f"{locked_app.vacancy.company_id}, skipping auto-reject"
            )
            return

        old_status = locked_app.status

        if old_status == ai_failed_status.key:
            logger.info(f"Application {locked_app.id} already in AI_FAILED, skipping auto-reject")
            return

        # Prevent overwriting recruiter's manual action — skip if terminal status
        is_terminal = ApplicationStatusModel.objects.filter(
            company=locked_app.vacancy.company,
            key=old_status,
            category__is_terminal=True,
        ).exists()

        if is_terminal:
            logger.info(
                f"Application {locked_app.id} already in terminal status {old_status}, "
                "skipping auto-reject to preserve recruiter action"
            )
            return

        locked_app._cached_old_status = old_status
        locked_app._cached_is_hired = False
        locked_app.status = ai_failed_status.key

        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
        note = (
            f"[{timestamp}] Auto-rejected by AI evaluation (score: {overall_score}/100). "
            f"The candidate's profile did not meet the minimum match threshold."
        )
        if locked_app.recruiter_notes:
            locked_app.recruiter_notes += f"\n\n{note}"
        else:
            locked_app.recruiter_notes = note

        locked_app.save(
            update_fields=["status", "recruiter_notes", "updated_at", "in_review_at", "hired_at"],
            skip_full_clean=True,
        )

        application = locked_app

        app_id = str(locked_app.id)
        db_transaction.on_commit(lambda: _enqueue_vacancy_roadmap(app_id))

    # Create conversation message for the status change
    try:
        create_status_change_message(
            application=application,
            old_status=old_status,
            new_status=ai_failed_status.key,
            recruiter_note=None,
            changed_by="SYSTEM",
        )
    except Exception as e:
        logger.warning(
            f"[AutoReject] Failed to create status change message for "
            f"application {application.id}: {e}"
        )

    # Send notification to candidate
    try:
        ApplicationNotificationService.notify_candidate_status_updated(
            application,
            old_status=old_status,
            new_status=ai_failed_status.key,
        )
    except Exception as e:
        logger.warning(
            f"[AutoReject] Failed to send rejection notification to candidate for "
            f"application {application.id}: {e}"
        )


def _handle_task_failure(
    job_queue_id: Optional[str],
    error_message: str,
    application_id: str,
    retry_attempt: int,
) -> None:
    """
    Update JobQueue to FAILED and re-enqueue if within retry limit.
    """
    from apps.general.models import JobQueue

    if not job_queue_id:
        return

    try:
        job = JobQueue.objects.get(id=job_queue_id)
    except JobQueue.DoesNotExist:
        return

    # Check retry eligibility BEFORE marking as failed (which increments retry_count)
    should_retry = job.can_retry
    job.mark_failed(error_message)

    if should_retry:
        queue = django_rq.get_queue("default")
        queue.enqueue_in(
            timedelta(minutes=5),
            process_candidate_ai_evaluation,
            application_id=application_id,
            job_queue_id=job_queue_id,
            retry_attempt=retry_attempt + 1,
            job_timeout=300,
        )
        logger.info(
            f"Re-enqueued evaluation retry {retry_attempt + 1} for application {application_id}"
        )


def _enqueue_vacancy_roadmap(application_id: str):
    django_rq.get_queue("high").enqueue(
        generate_vacancy_roadmap_task,
        application_id,
        job_timeout=300,
    )


def generate_vacancy_roadmap_task(application_id: str):
    from apps.applications.models import JobApplication
    from apps.student_analytics.services import generate_vacancy_roadmap

    try:
        application = JobApplication.objects.select_related(
            "vacancy", "candidate", "ai_evaluation", "resume_used"
        ).get(id=application_id)
    except JobApplication.DoesNotExist:
        logger.error(f"Application {application_id} not found for vacancy roadmap generation")
        return

    from apps.student_analytics.models import VacancySkillRoadmap as RoadmapModel
    try:
        application.vacancy_skill_roadmap
        logger.info(f"Vacancy roadmap already exists for application {application_id}")
        return
    except RoadmapModel.DoesNotExist:
        pass

    try:
        generate_vacancy_roadmap(application)
    except Exception:
        logger.exception(f"Failed to generate vacancy roadmap for application {application_id}")


def send_daily_application_report_task(report_date: Optional[str] = None) -> dict:
    """
    RQ task: build the daily application report and push it to Telegram.

    Scheduled once a day by ``apps.applications.services.scheduler``. Reports
    on the previous local day unless ``report_date`` (ISO ``YYYY-MM-DD``) is
    given, which is handy for manually re-sending a missed day.
    """
    from datetime import date as _date

    from apps.applications.services.daily_report import (
        build_daily_application_report,
        send_daily_application_report,
    )

    parsed_date = _date.fromisoformat(report_date) if report_date else None

    from apps.applications.models import DailyReportSnapshot

    try:
        payload = build_daily_application_report(report_date=parsed_date)
    except Exception:
        logger.exception("Failed to build daily application report")
        raise

    # Stored before delivery, and never allowed to fail it. Half of these
    # numbers describe the platform as it is right now and cannot be recomputed
    # for a past date, so the snapshot must not depend on Telegram being up —
    # and equally, a storage problem must not cost the group its report.
    stored = False
    try:
        stored = DailyReportSnapshot.store(payload) is not None
    except Exception:
        logger.exception(
            "Failed to store the daily report snapshot for %s",
            payload.get("report_date"),
        )

    delivered = send_daily_application_report(payload)
    return {
        "report_date": payload["report_date"],
        "applications": payload["totals"]["day"],
        "delivered": delivered,
        "stored": stored,
    }
