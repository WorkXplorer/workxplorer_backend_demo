import logging
from typing import List
from django.core.mail import send_mail
from django.template import Template, Context
from apps.general.models import EmailTemplate
from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_admin_alert_email(subject: str, message: str, recipient_list: List[str]) -> None:
    """
    Send an alert email to administrators.
    
    Args:
        subject: Email subject
        message: Email body message
        recipient_list: List of admin email addresses
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        logger.info(f"Admin alert email sent to {recipient_list}")
    except Exception as e:
        logger.error(f"Failed to send admin alert email: {str(e)}", exc_info=True)
        raise


def send_password_reset_email(to_email: str, context=None, language="uz"):
    """
    Send a password reset email using a stored EmailTemplate.

    The function retrieves an email template of type `password_reset`.
    If not found, it falls back to the first available template.

    Args:
        to_email (str): Recipient's email address.
        context (dict, optional): Context variables passed to the template.
            Expected keys:
                - user: User object
                - reset_url: Password reset link
                - site_name: Website name

    Raises:
        Exception: If no EmailTemplate is found or sending fails.
    """
    try:
        # Get the password reset template or fallback to the first available template
        template = EmailTemplate.objects.filter(
            template_type="reset-password", language=language
        ).first()

        if not template:
            logger.warning(
                f"Template not found for language: {language}, using fallback"
            )
            raise Exception("No EmailTemplate available!")

        ctx = Context(context or {})

        # Render subject from the template (subject is a CharField)
        subject_template = Template(template.subject)
        subject = subject_template.render(ctx)

        # Read and render HTML body from the uploaded file
        if template.body:
            template.body.open("r")
            html_content = template.body.read()
            template.body.close()
            body_template = Template(html_content)
            body = body_template.render(ctx)
        else:
            body = ""

        # Send the email
        send_mail(
            subject=subject,
            message=strip_tags(body),  # Fallback plain-text version
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=body,
            fail_silently=False,
        )
        logger.info(f"Password reset email sent to {to_email}")

    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}", exc_info=True)
        raise
