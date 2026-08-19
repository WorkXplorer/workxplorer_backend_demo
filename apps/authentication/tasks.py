import logging

logger = logging.getLogger(__name__)


def send_partner_notification_task(company_id: str) -> None:
    """
    RQ task: notify the Telegram partner topic about a new company registration.
    """
    from apps.authentication.services.telegram_notify import (
        notify_partner_registration,
    )

    notify_partner_registration(company_id)
