"""
Job Queue Service for managing RQ job retries and monitoring.

This service provides:
- Job registration for tracking analytics data sends
- Retry logic for failed jobs
- Alert system for jobs exceeding retry limits
- Daily cron job processing
"""

from __future__ import annotations

import logging
import hashlib
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

import django_rq

if TYPE_CHECKING:
    from apps.general.models import JobQueue

logger = logging.getLogger(__name__)


class JobQueueService:
    """
    Service to manage job queue operations including registration,
    retry handling, and alerting.
    """

    @staticmethod
    def _get_payload_hash(payload: Dict[str, Any]) -> str:
        """Generate a hash of the payload for duplicate detection."""
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(payload_str.encode()).hexdigest()

    @classmethod
    def register_job(
            cls,
            job_type: str,
            target_date: date,
            target_id: Optional[str] = None,
            target_name: Optional[str] = None,
            payload: Optional[Dict[str, Any]] = None,
    ) -> "JobQueue":
        """
        Register a new job or get existing job for the same target/date.
        """
        from apps.general.models import JobQueue

        payload_hash = cls._get_payload_hash(payload) if payload else None

        job, created = JobQueue.objects.get_or_create(
            job_type=job_type,
            target_date=target_date,
            target_id=target_id or "",
            defaults={
                "target_name": target_name,
                "status": JobQueue.JobStatus.PENDING,
                "payload_hash": payload_hash,
            }
        )

        if created:
            logger.info(
                f"Registered new job: {job_type} for {target_date} "
                f"(target_id={target_id}, target_name={target_name})"
            )
        else:
            if payload_hash and job.payload_hash != payload_hash:
                job.payload_hash = payload_hash
                job.save(update_fields=["payload_hash", "updated_at"])
            logger.debug(f"Job already exists: {job.id}")

        return job

    @classmethod
    def update_job_status(
            cls,
            job_id: str,
            status: str,
            error_message: Optional[str] = None,
            rq_job_id: Optional[str] = None,
    ) -> Optional["JobQueue"]:
        """
        Update the status of a job.
        """
        from apps.general.models import JobQueue

        try:
            job = JobQueue.objects.get(id=job_id)

            if status == JobQueue.JobStatus.PROCESSING:
                job.mark_processing()
                if rq_job_id:
                    job.rq_job_id = rq_job_id
                    job.save(update_fields=["rq_job_id"])
            elif status == JobQueue.JobStatus.COMPLETED:
                job.mark_completed()
            elif status == JobQueue.JobStatus.FAILED:
                job.mark_failed(error_message or "Unknown error")

            return job

        except JobQueue.DoesNotExist:
            logger.warning(f"Job not found: {job_id}")
            return None

    @classmethod
    def get_pending_and_failed_jobs(
            cls,
            job_type: Optional[str] = None,
            max_retries: int = 5,
    ) -> List["JobQueue"]:
        """
        Get all pending and failed jobs that can be retried.
        """
        from apps.general.models import JobQueue

        queryset = JobQueue.objects.filter(
            Q(status=JobQueue.JobStatus.PENDING) |
            Q(status=JobQueue.JobStatus.FAILED, retry_count__lte=max_retries)
        )

        if job_type:
            queryset = queryset.filter(job_type=job_type)

        return list(queryset.order_by("target_date", "created_at"))

    @classmethod
    def get_jobs_requiring_alert(cls) -> List["JobQueue"]:
        """
        Get all jobs that have exceeded retry limits and need alerting.
        """
        from apps.general.models import JobQueue

        return list(
            JobQueue.objects.filter(
                status=JobQueue.JobStatus.FAILED,
                retry_count__gt=settings.JOB_QUEUE_MAX_RETRIES,
                alert_sent=False,
            ).order_by("created_at")
        )

    @classmethod
    def send_alert_for_job(cls, job: "JobQueue") -> bool:
        """
        Send an alert for a job that has exceeded retry limits.
        """
        from apps.general.services.send_mail import send_admin_alert_email

        try:
            admin_emails = getattr(settings, "ADMIN_ALERT_EMAILS", [])

            if not admin_emails:
                logger.warning("No admin emails configured for alerts")
                job.alert_sent = True
                job.save(update_fields=["alert_sent", "updated_at"])
                return False

            subject = f"[WorkXplorer Alert] Job Failed - {job.job_type}"
            message = (
                f"A job has exceeded the maximum retry limit.\n\n"
                f"Job Details:\n"
                f"- Job ID: {job.id}\n"
                f"- Type: {job.job_type}\n"
                f"- Target Date: {job.target_date}\n"
                f"- Target ID: {job.target_id or 'N/A'}\n"
                f"- Target Name: {job.target_name or 'N/A'}\n"
                f"- Retry Count: {job.retry_count}\n"
                f"- Last Attempt: {job.last_attempt_at}\n"
                f"- Error Message: {job.error_message or 'N/A'}\n\n"
                f"Please investigate and resolve this issue."
            )

            django_rq.enqueue(send_admin_alert_email, subject, message, admin_emails)

            job.alert_sent = True
            job.save(update_fields=["alert_sent", "updated_at"])

            logger.info(f"Alert sent for job {job.id} to {admin_emails}")
            return True

        except Exception as e:
            logger.exception(f"Failed to send alert for job {job.id}: {e}")
            return False

    @classmethod
    def process_retry_jobs(cls) -> Dict[str, Any]:
        """
        Process all pending and failed jobs that need retrying.
        This is called by the daily cron job.
        """
        from apps.general.models import JobQueue

        results = {
            "processed": 0,
            "retried": 0,
            "alerts_sent": 0,
            "errors": [],
        }

        alert_jobs = cls.get_jobs_requiring_alert()
        for job in alert_jobs:
            if cls.send_alert_for_job(job):
                results["alerts_sent"] += 1

        retry_jobs = cls.get_pending_and_failed_jobs()

        for job in retry_jobs:
            results["processed"] += 1

            try:
                if job.job_type == JobQueue.JobType.EDU_ANALYTICS:
                    cls._retry_edu_analytics_job(job)
                    results["retried"] += 1
                elif job.job_type == JobQueue.JobType.HR_ANALYTICS:
                    cls._retry_hr_analytics_job(job)
                    results["retried"] += 1
                elif job.job_type == JobQueue.JobType.RESUME_GENERATION:
                    cls._retry_resume_generation_job(job)
                    results["retried"] += 1
                elif job.job_type == JobQueue.JobType.CANDIDATE_EVALUATION:
                    cls._retry_candidate_evaluation_job(job)
                    results["retried"] += 1
                else:
                    logger.warning(f"Unknown job type: {job.job_type}")

            except Exception as e:
                error_msg = f"Failed to retry job {job.id}: {str(e)}"
                logger.exception(error_msg)
                results["errors"].append(error_msg)
                job.mark_failed(str(e))

        logger.info(
            f"Retry processing complete: {results['processed']} processed, "
            f"{results['retried']} retried, {results['alerts_sent']} alerts sent"
        )

        return results

    @classmethod
    def _retry_edu_analytics_job(cls, job: "JobQueue") -> None:
        """Retry an EduPartner analytics job."""
        from apps.edupartners.tasks import send_single_faculty_analytics

        queue = django_rq.get_queue("default")
        job.mark_processing()
        rq_job = queue.enqueue(
            send_single_faculty_analytics,
            job.target_id,
            str(job.id),
            job_timeout="5m",
            meta={"faculty_id": job.target_id, "retry_attempt": job.retry_count},
        )
        job.rq_job_id = rq_job.id
        job.save(update_fields=["rq_job_id"])
        logger.info(f"Retried EduPartner analytics job {job.id}")

    @classmethod
    def _retry_hr_analytics_job(cls, job: "JobQueue") -> None:
        """Retry an HR analytics job."""
        from apps.general.tasks import send_single_company_analytics

        queue = django_rq.get_queue("default")
        job.mark_processing()
        rq_job = queue.enqueue(
            send_single_company_analytics,
            job.target_id,
            job_timeout="5m",
            job_queue_id=str(job.id),
            meta={"company_id": job.target_id, "retry_attempt": job.retry_count},
        )
        job.rq_job_id = rq_job.id
        job.save(update_fields=["rq_job_id"])
        logger.info(f"Retried HR analytics job {job.id}")

    @classmethod
    def _retry_resume_generation_job(cls, job: "JobQueue") -> None:
        """
        Retry a resume generation job via cron fallback.

        Note: Cron-based retry lacks the original prompt/file content,
        so immediate retry from _handle_task_failure is the primary
        mechanism. This method logs a warning and skips the retry.
        """
        logger.warning(
            f"Cron-based retry for resume generation job {job.id} skipped: "
            "original prompt/file content is not available. "
            "The immediate retry mechanism handles retries with full context."
        )

    @classmethod
    def _retry_candidate_evaluation_job(cls, job: "JobQueue") -> None:
        """
        Retry a candidate AI evaluation job.

        The application_id is stored as target_id on the JobQueue entry.
        """
        from apps.applications.tasks import process_candidate_ai_evaluation

        # Guard: respect max_retries — avoid double-retry with immediate retry
        # in _handle_task_failure which already re-enqueues on failure.
        if not job.can_retry:
            logger.warning(
                f"Skipping cron retry for evaluation job {job.id}: "
                f"retry_count {job.retry_count} >= max_retries {job.max_retries}"
            )
            return

        application_id = job.target_id
        if not application_id:
            logger.warning(f"Cannot retry evaluation job {job.id}: no target_id")
            return

        queue = django_rq.get_queue("default")
        job.mark_processing()
        rq_job = queue.enqueue(
            process_candidate_ai_evaluation,
            application_id=application_id,
            job_queue_id=str(job.id),
            retry_attempt=job.retry_count,
            job_timeout=300,
        )
        job.rq_job_id = rq_job.id
        job.save(update_fields=["rq_job_id"])
        logger.info(
            f"Retried candidate evaluation job {job.id} "
            f"(application_id={application_id}, retry={job.retry_count})"
        )

    @classmethod
    def cleanup_old_completed_jobs(cls, days_to_keep: int = 30) -> int:
        """
        Clean up old completed jobs to prevent table bloat.
        """
        from apps.general.models import JobQueue

        cutoff_date = timezone.now() - timedelta(days=days_to_keep)
        deleted_count, _ = JobQueue.objects.filter(
            status=JobQueue.JobStatus.COMPLETED,
            updated_at__lt=cutoff_date,
        ).delete()
        logger.info(f"Cleaned up {deleted_count} old completed jobs")
        return deleted_count

    @classmethod
    def get_job_statistics(cls) -> Dict[str, Any]:
        """
        Get statistics about job queue status.
        """
        from apps.general.models import JobQueue
        from django.db.models import Count

        stats = JobQueue.objects.values("job_type", "status").annotate(count=Count("id"))

        result = {
            "by_type": {},
            "by_status": {},
            "total": 0,
            "failed_needing_attention": 0,
        }

        for stat in stats:
            job_type = stat["job_type"]
            status = stat["status"]
            count = stat["count"]

            if job_type not in result["by_type"]:
                result["by_type"][job_type] = {}
            result["by_type"][job_type][status] = count

            if status not in result["by_status"]:
                result["by_status"][status] = 0
            result["by_status"][status] += count

            result["total"] += count

        result["failed_needing_attention"] = JobQueue.objects.filter(
            status=JobQueue.JobStatus.FAILED,
            retry_count__gt=settings.JOB_QUEUE_MAX_RETRIES,
            alert_sent=False,
        ).count()

        return result
