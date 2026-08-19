"""
Quiz email helpers.

Provides one function called from calculate_quiz.py:

- send_quiz_result_email  → case 1 (new anonymous email): career cards + register button
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator as token_generator

from apps.general.services.email_service import send_email_from_template_type
from utils import encode_uid

logger = logging.getLogger(__name__)


def send_quiz_result_email(candidate, career_options: list, language: str) -> None:
    """
    Send case-1 quiz result email: career cards + registration (set-password) CTA.

    Args:
        candidate:       Candidate instance that was just auto-created.
        career_options:  List of result dicts
        language:        'uz' | 'ru' | 'en'
    """
    try:
        uid = encode_uid(candidate.pk)
        token = token_generator.make_token(candidate)
        set_password_url = (
            f"{settings.FRONTEND_URL}/set-password/candidate/{uid}/{token}/"
        )

        context = {
            "user_email": candidate.email,
            "set_password_url": set_password_url,
            "site_name": getattr(settings, "SITE_NAME", "WorkXplorer"),
            "career_options": career_options,
        }

        send_email_from_template_type(
            to_email=candidate.email,
            template_type="quiz-result",
            context=context,
            language=language,
            delay_seconds=0,
        )

        logger.info("Quiz result email queued for candidate %s", candidate.id)
    except Exception:
        logger.exception(
            "Failed to queue quiz result email for candidate %s", candidate.id
        )
