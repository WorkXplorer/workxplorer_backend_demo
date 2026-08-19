import logging
import smtplib
from typing import Optional, Dict, Any
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template import Template, Context

from rq import Queue
from redis import Redis

from apps.general.models import EmailTemplate

logger = logging.getLogger(__name__)


class BaseEmailService:
    """
    Base class for email services.
    Provides common functionality for rendering and sending emails.
    """

    DEFAULT_QUEUE_NAME = "default"
    DEFAULT_JOB_TIMEOUT = 360

    @staticmethod
    def get_redis_connection():
        """
        Get Redis connection for queue operations.

        Returns:
            Redis connection instance
        """
        redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6380/0")
        return Redis.from_url(redis_url)

    @staticmethod
    def get_queue(queue_name: str = DEFAULT_QUEUE_NAME):
        """
        Get RQ queue instance.

        Args:
            queue_name: Name of the queue

        Returns:
            Queue instance
        """
        conn = BaseEmailService.get_redis_connection()
        return Queue(queue_name, connection=conn)

    @staticmethod
    def render_template(
            template: EmailTemplate, context: Optional[Dict[str, Any]] = None
    ) -> tuple[str, str]:
        """
        Render email template subject and body.

        Args:
            template: EmailTemplate instance
            context: Template context dictionary

        Returns:
            Tuple of (subject, body)
        """
        ctx = Context(context or {})

        # Render subject
        subject_template = Template(template.subject)
        subject = subject_template.render(ctx)

        # Read and render HTML body
        body = ""
        if template.body:
            template.body.open("r")
            html_content = template.body.read()
            template.body.close()
            body_template = Template(html_content)
            body = body_template.render(ctx)

        return subject, body

    @staticmethod
    def send_email(
            to_email: str,
            subject: str,
            body: str,
            plain_message: Optional[str] = None,
    ) -> bool:
        """
        Send an email using Django's send_mail with enhanced logging.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: HTML email body
            plain_message: Plain text fallback message (auto-generated from HTML if not provided)

        Returns:
            bool: True if successful, False otherwise
        """
        from django.utils.html import strip_tags
        import time

        logger.info("=" * 80)
        logger.info("[EMAIL SEND] Starting email send operation")
        logger.info(f"[EMAIL SEND] To: {to_email}")
        logger.info(f"[EMAIL SEND] Subject: {subject}")
        logger.info(f"[EMAIL SEND] From: {getattr(settings, 'DEFAULT_FROM_EMAIL', 'NOT_SET')}")
        logger.info(f"[EMAIL SEND] HTML body length: {len(body)} chars")

        # Generate plain text version if not provided
        if not plain_message:
            import re
            logger.info("[EMAIL SEND] Generating plain text version from HTML")
            clean_html = re.sub(r'<(style|script)[^>]*>.*?</(style|script)>', '', body, flags=re.DOTALL)
            plain_message = strip_tags(clean_html)
            plain_message = re.sub(r'\n{3,}', '\n\n', plain_message).strip()

        logger.info(f"[EMAIL SEND] Plain text preview: {plain_message[:150]}...") 
        
        # Log SMTP configuration
        logger.info("[EMAIL SEND] SMTP Configuration:")
        logger.info(f"[EMAIL SEND]   Backend: {getattr(settings, 'EMAIL_BACKEND', 'NOT_SET')}")
        logger.info(f"[EMAIL SEND]   Host: {getattr(settings, 'EMAIL_HOST', 'NOT_SET')}")
        logger.info(f"[EMAIL SEND]   Port: {getattr(settings, 'EMAIL_PORT', 'NOT_SET')}")
        logger.info(f"[EMAIL SEND]   TLS: {getattr(settings, 'EMAIL_USE_TLS', False)}")
        logger.info(f"[EMAIL SEND]   SSL: {getattr(settings, 'EMAIL_USE_SSL', False)}")
        logger.info(f"[EMAIL SEND]   User: {getattr(settings, 'EMAIL_HOST_USER', 'NOT_SET')}")

        try:
            start_time = time.time()
            logger.info("[EMAIL SEND] Calling Django send_mail()...")
            
            num_sent = send_mail(
                subject=subject,
                message=plain_message,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[to_email],
                html_message=body,
                fail_silently=False,
            )
            
            elapsed = time.time() - start_time
            logger.info(f"[EMAIL SEND] ✓ send_mail() completed in {elapsed:.2f}s")
            logger.info(f"[EMAIL SEND] ✓ Number of emails sent: {num_sent}")
            logger.info("[EMAIL SEND] ✓ Email successfully delivered to SMTP server")
            logger.info("=" * 80)
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error("=" * 80)
            logger.error("[EMAIL SEND] ✗ SMTP AUTHENTICATION ERROR")
            logger.error(f"[EMAIL SEND] Error code: {e.smtp_code}")
            logger.error(f"[EMAIL SEND] Error message: {e.smtp_error}")
            logger.error(f"[EMAIL SEND] Details: {str(e)}")
            logger.error("[EMAIL SEND] Possible causes:")
            logger.error("[EMAIL SEND]   - Incorrect EMAIL_HOST_USER or EMAIL_HOST_PASSWORD")
            logger.error("[EMAIL SEND]   - App-specific password required (Gmail, Outlook)")
            logger.error("[EMAIL SEND]   - Account security settings blocking login")
            logger.error("=" * 80, exc_info=True)
            raise
            
        except smtplib.SMTPConnectError as e:
            logger.error("=" * 80)
            logger.error("[EMAIL SEND] ✗ SMTP CONNECTION ERROR")
            logger.error(f"[EMAIL SEND] Error code: {e.smtp_code}")
            logger.error(f"[EMAIL SEND] Error message: {e.smtp_error}")
            logger.error(f"[EMAIL SEND] Details: {str(e)}")
            logger.error("[EMAIL SEND] Possible causes:")
            logger.error("[EMAIL SEND]   - SMTP server is down or unreachable")
            logger.error("[EMAIL SEND]   - Firewall blocking connection")
            logger.error("[EMAIL SEND]   - Incorrect EMAIL_HOST or EMAIL_PORT")
            logger.error("=" * 80, exc_info=True)
            raise
            
        except smtplib.SMTPServerDisconnected as e:
            logger.error("=" * 80)
            logger.error("[EMAIL SEND] ✗ SMTP SERVER DISCONNECTED")
            logger.error(f"[EMAIL SEND] Details: {str(e)}")
            logger.error("[EMAIL SEND] Possible causes:")
            logger.error("[EMAIL SEND]   - Connection timeout")
            logger.error("[EMAIL SEND]   - Server closed connection unexpectedly")
            logger.error("[EMAIL SEND]   - Network instability")
            logger.error("=" * 80, exc_info=True)
            raise
            
        except smtplib.SMTPException as e:
            logger.error("=" * 80)
            logger.error(f"[EMAIL SEND] ✗ SMTP ERROR: {type(e).__name__}")
            logger.error(f"[EMAIL SEND] Details: {str(e)}")
            logger.error("=" * 80, exc_info=True)
            raise
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"[EMAIL SEND] ✗ UNEXPECTED ERROR: {type(e).__name__}")
            logger.error(f"[EMAIL SEND] To: {to_email}")
            logger.error(f"[EMAIL SEND] Subject: {subject}")
            logger.error(f"[EMAIL SEND] Details: {str(e)}")
            logger.error("=" * 80, exc_info=True)
            raise

    @staticmethod
    def enqueue_job(
            worker_func,
            *args,
            delay_seconds: int = 0,
            queue_name: str = DEFAULT_QUEUE_NAME,
            job_timeout: int = DEFAULT_JOB_TIMEOUT,
            **kwargs,
    ):
        """
        Enqueue a job to be processed by RQ worker.

        Args:
            worker_func: Worker function to execute
            *args: Positional arguments for worker function
            delay_seconds: Delay before executing job
            queue_name: Name of the queue
            job_timeout: Job timeout in seconds
            **kwargs: Keyword arguments for worker function

        Returns:
            Job object if successful
        """
        try:
            logger.info(f"[ENQUEUE_JOB] Getting RQ queue '{queue_name}'...")
            q = BaseEmailService.get_queue(queue_name)
            logger.info("[ENQUEUE_JOB] ✓ Queue connection established")
            logger.info(f"[ENQUEUE_JOB] Queue size: {len(q)} pending jobs")

            if delay_seconds > 0:
                logger.info(f"[ENQUEUE_JOB] Scheduling delayed job (delay: {delay_seconds}s)...")
                job = q.enqueue_in(
                    timedelta(seconds=delay_seconds),
                    worker_func,
                    *args,
                    job_timeout=job_timeout,
                    **kwargs,
                )
                logger.info(f"[ENQUEUE_JOB] ✓ Scheduled job {job.id} in {delay_seconds}s")
                logger.info(f"[ENQUEUE_JOB] Worker function: {worker_func.__name__}")
            else:
                logger.info("[ENQUEUE_JOB] Enqueueing immediate job...")
                job = q.enqueue(worker_func, *args, job_timeout=job_timeout, **kwargs)
                logger.info(f"[ENQUEUE_JOB] ✓ Queued job {job.id}")
                logger.info(f"[ENQUEUE_JOB] Worker function: {worker_func.__name__}")
                logger.info(f"[ENQUEUE_JOB] Timeout: {job_timeout}s")

            return job
            
        except Exception as e:
            logger.error(f"[ENQUEUE_JOB] ✗ Failed to enqueue job: {type(e).__name__}: {e}", exc_info=True)
            raise

    @staticmethod
    def get_email_template(
            template_type: str, language: str = "uz"
    ) -> Optional[EmailTemplate]:
        """
        Get email template by type and language.

        Args:
            template_type: Template type identifier
            language: Language code (default: 'uz')

        Returns:
            EmailTemplate instance or None
        """
        # Prefer exact language match, fallback to any template with given type
        template = (
                EmailTemplate.objects.filter(
                    template_type=template_type, language=language
                ).first()
                or EmailTemplate.objects.filter(template_type=template_type).first()
        )

        if not template:
            logger.error(
                f"No EmailTemplate found for type={template_type} language={language}"
            )

        return template
