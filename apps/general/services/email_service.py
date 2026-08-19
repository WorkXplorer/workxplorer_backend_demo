import logging

from rq.job import Job

from .base_email_service import BaseEmailService

logger = logging.getLogger(__name__)


def _send_password_reset_email_worker(to_email: str, context=None, language="uz"):
    """
    Worker task: sends password reset email.
    This runs inside an RQ worker process.
    """
    logger.info("=" * 80)
    logger.info("[WORKER] RQ Password Reset Job Started")
    logger.info(f"[WORKER] Recipient: {to_email}")
    logger.info(f"[WORKER] Language: {language}")
    logger.info("=" * 80)

    try:
        logger.info("[WORKER] Step 1/3: Fetching reset-password template...")
        template = BaseEmailService.get_email_template("reset-password", language)

        if not template:
            logger.error("=" * 80)
            logger.error("[WORKER] ✗ TEMPLATE NOT FOUND")
            logger.error("[WORKER] Template type: reset-password")
            logger.error(f"[WORKER] Language: {language}")
            logger.error("=" * 80)
            return False

        logger.info(f"[WORKER] ✓ Template found: {template.name}")

        # Render template
        logger.info("[WORKER] Step 2/3: Rendering template...")
        subject, body = BaseEmailService.render_template(template, context)
        logger.info(f"[WORKER] ✓ Template rendered: {subject}")

        # Send the email
        logger.info("[WORKER] Step 3/3: Sending email via SMTP...")
        BaseEmailService.send_email(
            to_email=to_email,
            subject=subject,
            body=body,
        )

        logger.info("=" * 80)
        logger.info("[WORKER] ✓ PASSWORD RESET JOB COMPLETED")
        logger.info(f"[WORKER] Email sent to {to_email}")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error("=" * 80)
        logger.error("[WORKER] ✗ PASSWORD RESET JOB FAILED")
        logger.error(f"[WORKER] Recipient: {to_email}")
        logger.error(f"[WORKER] Error: {type(e).__name__}: {e}")
        logger.error("=" * 80, exc_info=True)
        raise


def send_password_reset_email(
        to_email: str, context=None, language="uz", delay_seconds: int = 0
):
    """
    Queue password reset email to be sent via Redis Queue.

    Args:
        to_email: Recipient email address
        context: Template context dictionary
        language: Email language (default: 'uz')
        delay_seconds: Delay before sending (0 = immediate)

    Returns:
        Job object if successful
    """
    logger.info(f"[ENQUEUE] Preparing password reset email for {to_email}")

    try:
        job = BaseEmailService.enqueue_job(
            _send_password_reset_email_worker,
            to_email,
            context,
            language,
            delay_seconds=delay_seconds,
        )
        return job

    except Exception as e:
        logger.error(
            f"[ENQUEUE] Failed to enqueue password reset email for {to_email}: {str(e)}",
            exc_info=True,
        )
        raise


def _send_email_from_template_worker(
        to_email: str,
        template_type: str,
        context: dict | None = None,
        language: str = "uz",
):
    """
    Worker task: sends email using a stored EmailTemplate.
    This runs inside an RQ worker process.
    """
    logger.info("=" * 80)
    logger.info("[WORKER] RQ Email Job Started")
    logger.info(f"[WORKER] Recipient: {to_email}")
    logger.info(f"[WORKER] Template Type: {template_type}")
    logger.info(f"[WORKER] Language: {language}")
    logger.info(f"[WORKER] Context keys: {list(context.keys()) if context else 'None'}")
    logger.info("=" * 80)

    try:
        # Step 1: Fetch template
        logger.info("[WORKER] Step 1/3: Fetching EmailTemplate...")
        template = BaseEmailService.get_email_template(template_type, language)

        if not template:
            logger.error("=" * 80)
            logger.error("[WORKER] ✗ TEMPLATE NOT FOUND")
            logger.error(f"[WORKER] Template type: {template_type}")
            logger.error(f"[WORKER] Language: {language}")
            logger.error("[WORKER] Check if EmailTemplate exists in database")
            logger.error("=" * 80)
            return False

        logger.info(f"[WORKER] ✓ Template found: {template.name}")

        # Step 2: Render template
        logger.info("[WORKER] Step 2/3: Rendering template...")
        subject, body = BaseEmailService.render_template(template, context)
        logger.info("[WORKER] ✓ Template rendered")
        logger.info(f"[WORKER]   Subject: {subject}")
        logger.info(f"[WORKER]   Body length: {len(body)} chars")

        # Step 3: Send email
        logger.info("[WORKER] Step 3/3: Sending email via SMTP...")
        BaseEmailService.send_email(
            to_email=to_email,
            subject=subject,
            body=body,
        )

        logger.info("=" * 80)
        logger.info("[WORKER] ✓ JOB COMPLETED SUCCESSFULLY")
        logger.info(f"[WORKER] Email sent to {to_email} using template {template_type}")
        logger.info("=" * 80)
        return True

    except Exception as e:
        logger.error("=" * 80)
        logger.error("[WORKER] ✗ JOB FAILED")
        logger.error(f"[WORKER] Recipient: {to_email}")
        logger.error(f"[WORKER] Template: {template_type}")
        logger.error(f"[WORKER] Error type: {type(e).__name__}")
        logger.error(f"[WORKER] Error message: {str(e)}")
        logger.error("=" * 80, exc_info=True)
        raise


def send_email_from_template_type(
        to_email: str,
        template_type: str,
        context: dict | None = None,
        language: str = "uz",
        delay_seconds: int = 0,
):
    """
    Queue an email to be sent using a stored EmailTemplate via Redis Queue.

    Args:
        to_email: recipient email
        template_type: template_type value to search (e.g. "reset-password")
        context: template context dict
        language: language code to prefer
        delay_seconds: Delay before sending (0 = immediate)

    Returns:
        Job object if successful
    """
    logger.info("=" * 80)
    logger.info("[ENQUEUE] Email Job Queueing Request")
    logger.info(f"[ENQUEUE] Recipient: {to_email}")
    logger.info(f"[ENQUEUE] Template: {template_type}")
    logger.info(f"[ENQUEUE] Language: {language}")
    logger.info(f"[ENQUEUE] Delay: {delay_seconds}s")
    logger.info("=" * 80)
    
    try:
        job = BaseEmailService.enqueue_job(
            _send_email_from_template_worker,
            to_email,
            template_type,
            context,
            language,
            delay_seconds=delay_seconds,
        )
        
        logger.info("[ENQUEUE] ✓ Job successfully queued")
        logger.info(f"[ENQUEUE] Job ID: {job.id}")
        logger.info(f"[ENQUEUE] Job status: {job.get_status()}")
        logger.info(f"[ENQUEUE] Queue: {job.origin}")
        logger.info("=" * 80)
        
        return job

    except Exception as e:
        logger.error("=" * 80)
        logger.error("[ENQUEUE] ✗ Failed to queue email job")
        logger.error(f"[ENQUEUE] Recipient: {to_email}")
        logger.error(f"[ENQUEUE] Template: {template_type}")
        logger.error(f"[ENQUEUE] Error: {type(e).__name__}: {str(e)}")
        logger.error("=" * 80, exc_info=True)
        raise


def get_job_status(job_id: str):
    """
    Check the status of a queued job.

    Returns:
        dict with job status information or None if not found
    """
    try:
        conn = BaseEmailService.get_redis_connection()

        job = Job.fetch(job_id, connection=conn)

        return {
            "id": job.id,
            "status": job.get_status(),
            "created_at": job.created_at,
            "enqueued_at": job.enqueued_at,
            "started_at": job.started_at,
            "ended_at": job.ended_at,
            "result": job.result,
            "exc_info": job.exc_info,
        }
    except Exception as e:
        logger.error(f"Failed to fetch job {job_id}: {e}")
        return None


def get_queue_info():
    """
    Get information about the current queue.

    Returns:
        dict with queue statistics
    """
    try:
        q = BaseEmailService.get_queue()

        return {
            "name": q.name,
            "count": len(q),
            "scheduled_count": q.scheduled_job_registry.count,
            "started_count": q.started_job_registry.count,
            "finished_count": q.finished_job_registry.count,
            "failed_count": q.failed_job_registry.count,
        }
    except Exception as e:
        logger.error(f"Failed to get queue info: {e}")
        return None
