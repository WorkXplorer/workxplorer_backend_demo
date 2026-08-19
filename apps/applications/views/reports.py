"""
Internal endpoint for triggering the daily application report on demand.

Called by the Telegram bot's ``/report`` command. Authentication is a shared
secret rather than a user session: the caller is a service, not a person, and it
is the same secret the bot already validates on the inbound direction.

The work is queued rather than run inline — building the report and posting it
to Telegram takes seconds and can retry, so the request returns immediately and
the report arrives through the normal push path.
"""

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@extend_schema(
    summary="Trigger the daily application report",
    description=(
        "Queues the daily application report for delivery to the Telegram "
        "group. Requires the X-API-Secret header. Intended for the Telegram "
        "bot's /report command, not for browser clients."
    ),
    request=None,
    responses={202: None, 403: None, 503: None},
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def trigger_daily_report_view(request):
    """Queue the daily application report, optionally for a specific date."""
    expected_secret = getattr(settings, "TELEGRAM_BOT_API_SECRET", "")
    if not expected_secret:
        logger.error("TELEGRAM_BOT_API_SECRET not configured — cannot trigger report")
        return Response(
            {"detail": "Report delivery is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if request.headers.get("X-API-Secret") != expected_secret:
        logger.warning("Rejected daily report trigger with an invalid API secret")
        return Response(
            {"detail": "Invalid API secret."}, status=status.HTTP_403_FORBIDDEN
        )

    report_date = (request.data or {}).get("report_date") or None

    import django_rq

    from apps.applications.tasks import send_daily_application_report_task

    queue = django_rq.get_queue("default")
    job = queue.enqueue(
        send_daily_application_report_task,
        report_date=report_date,
        job_timeout=600,
    )

    logger.info(
        "Queued daily application report on demand (job=%s, report_date=%s)",
        job.id,
        report_date or "yesterday",
    )
    return Response(
        {"detail": "Report queued.", "job_id": job.id, "report_date": report_date},
        status=status.HTTP_202_ACCEPTED,
    )
