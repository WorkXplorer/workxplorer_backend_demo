"""
RQ tasks for HR Analytics data collection and sending.
Similar to EduPartner's tasks.py pattern.

This module handles:
- Collecting company analytics data and sending via protobuf
- Collecting vacancy analytics data and sending via a separate webhook
- Encoding data using protobuf
- Sending data to external HR Analytics service via RQ
- Registering jobs in JobQueue for retry tracking
"""

import logging
import requests
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from apps.general.services.analytics import HRAnalyticsService, HRAnalyticsProtobufService
from apps.general.services.analytics.vacancy_protobuf_service import VacancyAnalyticsProtobufService
from apps.general.services.analytics.vacancy.build import (
    build_vacancy_analytics_data,
)
from apps.general.services.analytics.utils import serialize_value
from utils.int_setting import parse_int_setting

logger = logging.getLogger(__name__)


# External HR analytics endpoints (company and vacancy are separate)
HR_ANALYTICS_COMPANY_WEBHOOK_URL = getattr(
    settings,
    "HR_ANALYTICS_COMPANY_WEBHOOK_URL",
    "https://hr-analytics.workxplorer.uz/api/analytics",
)

HR_ANALYTICS_VACANCY_WEBHOOK_URL = getattr(
    settings,
    "HR_ANALYTICS_VACANCY_WEBHOOK_URL",
    "https://hr-analytics.workxplorer.uz/api/analytics/vacancy",
)

HH_MARKET_SYNC_DEFAULT_AREA_ID = getattr(settings, "HH_MARKET_SYNC_AREA_ID", "97")
HH_MARKET_SYNC_DEFAULT_PAGES = parse_int_setting(
    getattr(settings, "HH_MARKET_SYNC_PAGES", 2),
    2,
    minimum=1,
    maximum=5,
)
HH_MARKET_SYNC_DEFAULT_PER_PAGE = parse_int_setting(
    getattr(settings, "HH_MARKET_SYNC_PER_PAGE", 30),
    30,
    minimum=1,
    maximum=100,
)


def _get_job_queue_service():
    """Lazy import to avoid circular imports."""
    from apps.general.services.job_queue_service import JobQueueService
    return JobQueueService


def _get_job_queue_model():
    """Lazy import to avoid circular imports."""
    from apps.general.models import JobQueue
    return JobQueue


def sync_hh_market_skills(
        domain_ids: Optional[List[str]] = None,
        area_id: str = HH_MARKET_SYNC_DEFAULT_AREA_ID,
        max_pages: int = HH_MARKET_SYNC_DEFAULT_PAGES,
        per_page: int = HH_MARKET_SYNC_DEFAULT_PER_PAGE,
        language: str = "uz",
) -> Dict[str, Any]:
    """
    RQ task for the periodic HH market refresh.
    Fetches HH vacancies per domain, extracts skills, and stores raw market
    skills without creating canonical Skill rows.
    """
    from apps.domain.models import Domain
    from apps.general.services.hh_client import collect_hh_api_vacancies
    from apps.general.services.market_skill_cache import upsert_domain_market_skills
    from apps.skills.localization import clean_text

    queryset = Domain.objects.all().order_by("name")
    if domain_ids:
        queryset = queryset.filter(id__in=domain_ids)

    market_skill_count = 0
    failed = []

    for domain in queryset:
        query = clean_text(domain.name)
        if not query:
            continue

        try:
            vacancies = collect_hh_api_vacancies(
                query=query,
                area_id=area_id,
                max_pages=max_pages,
                per_page=per_page,
            )
            rows, _ = upsert_domain_market_skills(
                query=query,
                vacancies=vacancies,
                area_id=area_id,
                language=language,
                domain=domain,
            )
            market_skill_count += len(rows)
        except Exception as exc:
            error_message = str(exc)
            failed.append(
                {
                    "domain_id": str(domain.id),
                    "query": query,
                    "error": error_message,
                }
            )

    return {
        "status": "completed" if not failed else "partial",
        "market_skills_synced": market_skill_count,
        "failed": failed,
    }


def sync_stat_uz_sector_salaries() -> Dict[str, Any]:
    """
    RQ task for the periodic stat.uz sector salary refresh. Pulls the full
    sector salary table (quarterly, official) so the calculator can sanity-
    check its HH-derived estimate against it.
    """
    from apps.general.services.stat_uz_sector_salary import (
        sync_stat_uz_sector_salaries as sync_sector_salaries,
    )

    try:
        synced = sync_sector_salaries()
        return {"status": "completed", "rows_synced": synced}
    except Exception as exc:
        logger.warning("Failed to sync stat.uz sector salaries", exc_info=True)
        return {"status": "failed", "error": str(exc)}


def classify_domain_sectors_task() -> Dict[str, Any]:
    """
    RQ task for the monthly Domain -> stat.uz sector_code classification
    pass. See apps.domain.services.sector_classification for the logic.
    """
    from apps.domain.services.sector_classification import classify_domain_sectors

    try:
        return classify_domain_sectors()
    except Exception as exc:
        logger.warning("Failed to run domain sector classification", exc_info=True)
        return {"status": "failed", "error": str(exc)}


def send_single_company_analytics(
        company_id: str,
        analytics_end_date: Optional[datetime] = None,
        analytics_period_days: int = 30,
        job_queue_id: str = None,
) -> Dict[str, Any]:
    """
    RQ task to collect and send analytics for a single company.
    This ensures each company only receives their own statistics.

    Args:
        company_id: UUID string of the company
        analytics_end_date: End date for analytics period
        analytics_period_days: Length of analytics period in days
        job_queue_id: Optional UUID string of the JobQueue record for tracking

    Returns:
        Dictionary with status and result info
    """
    JobQueueService = _get_job_queue_service()
    JobQueue = _get_job_queue_model()
    job = None

    try:
        # Convert string to UUID if needed
        if isinstance(company_id, str):
            company_id_uuid = UUID(company_id)
        else:
            company_id_uuid = company_id
            company_id = str(company_id)

        # Collect analytics for this specific company
        analytics_data = HRAnalyticsService.get_company_analytics(
            company_id=str(company_id_uuid),
            end_date=analytics_end_date,
            period_days=analytics_period_days,
        )

        if not analytics_data:
            logger.warning(f"No analytics data for company {company_id}")
            return {
                "status": "warning",
                "reason": "no_analytics_data",
                "company_id": company_id,
            }

        # Get company name for job registration
        company_name = analytics_data.get("company", {}).get("name", "Unknown")

        # Try to use existing JobQueue record if job_queue_id is provided (e.g., for retries)
        if job_queue_id:
            try:
                job = JobQueue.objects.get(id=job_queue_id)
            except JobQueue.DoesNotExist:
                logger.warning(
                    "JobQueue with id %s does not exist; registering new job for company %s",
                    job_queue_id,
                    company_id,
                )
                job = None

        # Register new job in JobQueue only if no existing job was found
        if job is None:
            job = JobQueueService.register_job(
                job_type=JobQueue.JobType.HR_ANALYTICS,
                target_date=date.today(),
                target_id=company_id,
                target_name=company_name,
                payload=analytics_data,
            )

        # Mark job as processing
        job.mark_processing()

        # Send data to external HR analytics service
        result = _send_analytics_to_service(analytics_data, company_id)

        # Mark job as completed
        job.mark_completed()

        logger.info(
            f"Successfully sent analytics for company: "
            f"{company_name} (company_id={company_id})"
        )

        return {
            "status": "success",
            "company_id": company_id,
            "company_name": company_name,
            "send_result": result,
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Failed to send analytics for company {company_id}: {e}")

        # Mark job as failed if we have a job record
        if job:
            job.mark_failed(error_msg)
        else:
            # Create a failed job record for tracking
            try:
                job = JobQueueService.register_job(
                    job_type=JobQueue.JobType.HR_ANALYTICS,
                    target_date=date.today(),
                    target_id=company_id,
                    target_name=None,
                )
                job.mark_failed(error_msg)
            except Exception as reg_error:
                logger.warning(f"Failed to register failed job: {reg_error}")

        return {
            "status": "error",
            "company_id": company_id,
            "error": error_msg,
        }


def send_hr_analytics_data() -> Dict[str, Any]:
    """
    RQ task to enqueue individual analytics jobs for each active company.
    Creates a separate job per company to ensure data isolation.

    Returns:
        Dictionary with enqueue results
    """
    import django_rq

    failed_company_ids = []

    try:
        # Get all active company IDs
        company_ids = HRAnalyticsService.get_company_ids()

        if not company_ids:
            logger.info("No active companies found")
            return {
                "status": "completed",
                "companies_processed": 0,
                "message": "No active companies found",
            }

        logger.info(f"Enqueuing analytics jobs for {len(company_ids)} companies")

        # Get the default queue
        queue = django_rq.get_queue("default")

        # Enqueue a separate job for each company
        jobs_enqueued = 0
        for company_id in company_ids:
            try:
                queue.enqueue(
                    send_single_company_analytics,
                    str(company_id),
                    job_timeout="5m",
                    meta={"company_id": str(company_id)},
                )
                jobs_enqueued += 1
                logger.debug(f"Enqueued analytics job for company {company_id}")
            except Exception as e:
                logger.warning(f"Failed to enqueue job for company {company_id}: {e}")
                failed_company_ids.append(company_id)

        logger.info(f"Successfully enqueued {jobs_enqueued} company analytics jobs")

        return {
            "status": "completed",
            "companies_processed": len(company_ids),
            "jobs_enqueued": jobs_enqueued,
            "failed_company_ids": failed_company_ids,
        }

    except Exception as e:
        logger.exception(f"Failed to enqueue company analytics jobs: {e}")
        return {
            "status": "error",
            "error": str(e),
            "failed_company_ids": failed_company_ids,
        }


def _send_analytics_to_service(
        analytics_data: Dict[str, Any],
        company_id: str
) -> Dict[str, Any]:
    """
    Send company analytics data to the external HR analytics service using protobuf encoding.

    Args:
        analytics_data: Dictionary containing analytics for a single company
        company_id: UUID string of the company

    Returns:
        Dictionary with send status and info
    """
    try:
        # Validate data before encoding
        if not HRAnalyticsProtobufService.validate_analytics_data(analytics_data):
            logger.error("HR analytics data validation failed, aborting send.")
            raise ValueError("Invalid analytics data payload; validation failed")
        # Encode data using PURE protobuf
        protobuf_data = HRAnalyticsProtobufService.encode_analytics_data(analytics_data)

        # Build company-specific webhook URL
        base_url = HR_ANALYTICS_COMPANY_WEBHOOK_URL.rstrip("/")
        webhook_url = f"{base_url}/{company_id}/"

        # Send to external service with protobuf content
        response = requests.post(
            webhook_url,
            data=protobuf_data,
            headers={
                "Content-Type": "application/x-protobuf",
                "Content-Encoding": "protobuf",
                "X-Data-Format": "workxplorer-protobuf-v3",
            },
            timeout=30,
        )

        response.raise_for_status()

        logger.info(
            f"PURE protobuf analytics sent successfully for company {company_id} "
            f"(size: {len(protobuf_data)} bytes, status: {response.status_code})"
        )

        return {
            "status": "ok",
            "status_code": response.status_code,
            "protobuf_size": len(protobuf_data),
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send protobuf analytics to HR service: {e}")
        raise

    except Exception as e:
        logger.error(f"Failed to encode or send analytics: {e}")
        raise


# ---------------------------------------------------------------------------
# Vacancy Analytics Webhook (dedicated endpoint)
# ---------------------------------------------------------------------------


def _get_vacancies_for_analytics(company_id: str) -> List:
    """
    Get vacancies that need their analytics sent to HR Analytics.

    Includes:
      - All active vacancies (is_active=True).
      - Inactive vacancies whose deactivation has **not** yet been
        successfully delivered (``deactivation_synced_at IS NULL``).

    Excludes:
      - Inactive vacancies whose deactivation was already synced.

    Side-effect:
      If a vacancy was previously synced as deactivated but is now
      active again (reactivated), its sync record is cleared so it
      re-enters the normal cycle.
    """
    from apps.vacancies.models import Vacancy
    from apps.general.models import VacancyAnalyticsSync

    # IDs of vacancies whose deactivation was already synced
    synced_ids = set(
        VacancyAnalyticsSync.objects.filter(
            deactivation_synced_at__isnull=False,
        ).values_list("vacancy_id", flat=True)
    )

    vacancies = list(
        Vacancy.objects.filter(
            company_id=company_id,
        ).select_related(
            "domain",
            "created_by",
        ).order_by("-updated_at")
    )

    result = []
    reactivated_ids = []

    for v in vacancies:
        if v.is_active:
            result.append(v)
            # Vacancy was previously synced as deactivated but is now active
            if v.id in synced_ids:
                reactivated_ids.append(v.id)
        else:
            # Inactive: include only if deactivation not yet synced
            if v.id not in synced_ids:
                result.append(v)

    # Clear deactivation sync for reactivated vacancies
    if reactivated_ids:
        VacancyAnalyticsSync.objects.filter(
            vacancy_id__in=reactivated_ids,
        ).update(deactivation_synced_at=None)
        logger.info(
            f"Cleared deactivation sync for {len(reactivated_ids)} "
            f"reactivated vacancies (company={company_id})"
        )

    return result


def _mark_deactivation_synced(vacancy_id: str) -> None:
    """
    Record that a deactivated vacancy's final is_active=False update
    was successfully delivered to HR Analytics.
    """
    from apps.general.models import VacancyAnalyticsSync

    VacancyAnalyticsSync.objects.update_or_create(
        vacancy_id=vacancy_id,
        defaults={"deactivation_synced_at": timezone.now()},
    )


def _build_vacancy_payload(
        vacancy,
        company_id: str,
) -> Dict[str, Any]:
    """
    Build the vacancy analytics payload for a single vacancy.

    Args:
        vacancy: Vacancy model instance
        company_id: UUID string of the company

    Returns:
        Dictionary ready for protobuf encoding and sending
    """
    vacancy_data = build_vacancy_analytics_data(vacancy)

    return {
        "source": "workxplorer",
        "timestamp": serialize_value(timezone.now()),
        "meta": {
            "env": getattr(settings, "ENVIRONMENT", "unknown"),
            "company_id": str(company_id),
            "vacancy_id": str(vacancy.id),
        },
        "vacancy": vacancy_data,
        "analytics_timestamp": serialize_value(timezone.now()),
    }


def _send_vacancy_to_service(
        vacancy_payload: Dict[str, Any],
        company_id: str,
        vacancy_id: str,
) -> Dict[str, Any]:
    """
    Send vacancy analytics data to the dedicated vacancy webhook using protobuf.

    Args:
        vacancy_payload: Validated vacancy analytics payload
        company_id: UUID string of the company
        vacancy_id: UUID string of the vacancy

    Returns:
        Dictionary with send status and info
    """
    try:
        if not VacancyAnalyticsProtobufService.validate_vacancy_data(vacancy_payload):
            logger.error(f"Vacancy analytics data validation failed for vacancy {vacancy_id}")
            raise ValueError("Invalid vacancy analytics payload; validation failed")

        protobuf_data = VacancyAnalyticsProtobufService.encode_vacancy_data(vacancy_payload)

        # Build vacancy-specific webhook URL: .../vacancy/{vacancy_id}/
        base_url = HR_ANALYTICS_VACANCY_WEBHOOK_URL.rstrip("/")
        webhook_url = f"{base_url}/{vacancy_id}/"

        response = requests.post(
            webhook_url,
            data=protobuf_data,
            headers={
                "Content-Type": "application/x-protobuf",
                "Content-Encoding": "protobuf",
                "X-Data-Format": "workxplorer-vacancy-protobuf-v1",
            },
            timeout=30,
        )

        response.raise_for_status()

        logger.info(
            f"Vacancy protobuf analytics sent successfully for vacancy {vacancy_id} "
            f"(company={company_id}, size={len(protobuf_data)} bytes, "
            f"status={response.status_code})"
        )

        return {
            "status": "ok",
            "status_code": response.status_code,
            "protobuf_size": len(protobuf_data),
        }

    except requests.exceptions.RequestException as e:
        logger.error(
            f"Failed to send vacancy protobuf analytics for vacancy {vacancy_id}: {e}"
        )
        raise

    except Exception as e:
        logger.error(f"Failed to encode or send vacancy analytics: {e}")
        raise


def send_single_company_vacancy_analytics(
        company_id: str,
        job_queue_id: str = None,
) -> Dict[str, Any]:
    """
    RQ task to collect and send vacancy analytics for all relevant vacancies
    of a single company to the dedicated vacancy webhook.

    Active vacancies are always sent.
    Vacancies that became inactive within the last 4 hours are sent once
    (with is_active=False) so the analytics service knows they are archived.

    Args:
        company_id: UUID string of the company
        job_queue_id: Optional UUID string of the JobQueue record for tracking

    Returns:
        Dictionary with status and result info
    """
    JobQueueService = _get_job_queue_service()
    JobQueue = _get_job_queue_model()
    job = None

    try:
        if isinstance(company_id, str):
            # Validate that company_id is a proper UUID string
            UUID(company_id)
        else:
            company_id = str(company_id)

        vacancies = _get_vacancies_for_analytics(company_id)

        if not vacancies:
            logger.info(f"No vacancies to send for company {company_id}")
            return {
                "status": "completed",
                "reason": "no_vacancies",
                "company_id": company_id,
                "vacancies_sent": 0,
            }

        # Register job in JobQueue for tracking
        if job_queue_id:
            try:
                job = JobQueue.objects.get(id=job_queue_id)
            except JobQueue.DoesNotExist:
                job = None

        if job is None:
            job = JobQueueService.register_job(
                job_type=JobQueue.JobType.HR_ANALYTICS,
                target_date=date.today(),
                target_id=company_id,
                target_name=f"vacancy_analytics_{company_id}",
                payload={"vacancy_count": len(vacancies)},
            )

        job.mark_processing()

        sent_count = 0
        deactivation_synced_count = 0
        failed_vacancies = []

        for vacancy in vacancies:
            try:
                vacancy_payload = _build_vacancy_payload(vacancy, company_id)
                _send_vacancy_to_service(
                    vacancy_payload, company_id, str(vacancy.id)
                )
                sent_count += 1

                # Mark deactivation as synced after successful delivery
                if not vacancy.is_active:
                    _mark_deactivation_synced(str(vacancy.id))
                    deactivation_synced_count += 1
                    logger.info(
                        f"Final deactivation update delivered for "
                        f"vacancy {vacancy.id} (company={company_id})"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to send vacancy {vacancy.id} analytics: {e}"
                )
                failed_vacancies.append(str(vacancy.id))

        # Mark job status based on results
        if failed_vacancies:
            # Partial or complete failure - mark as failed with details
            error_msg = f"Failed to send {len(failed_vacancies)} vacancies: {', '.join(failed_vacancies[:5])}{'...' if len(failed_vacancies) > 5 else ''}"
            job.mark_failed(error_msg)
            logger.warning(
                f"Vacancy analytics partially failed for company {company_id}: "
                f"{sent_count} sent, {len(failed_vacancies)} failed"
            )
        else:
            job.mark_completed()
            logger.info(
                f"Vacancy analytics successfully sent for company {company_id}: "
                f"{sent_count} vacancies ({deactivation_synced_count} deactivation syncs)"
            )

        return {
            "status": "partial_success" if failed_vacancies else "success",
            "company_id": company_id,
            "vacancies_sent": sent_count,
            "deactivation_synced": deactivation_synced_count,
            "failed_vacancies": failed_vacancies,
        }

    except Exception as e:
        error_msg = str(e)
        logger.exception(
            f"Failed to send vacancy analytics for company {company_id}: {e}"
        )

        if job:
            job.mark_failed(error_msg)
        else:
            try:
                job = JobQueueService.register_job(
                    job_type=JobQueue.JobType.HR_ANALYTICS,
                    target_date=date.today(),
                    target_id=company_id,
                    target_name=f"vacancy_analytics_{company_id}",
                )
                job.mark_failed(error_msg)
            except Exception as reg_error:
                logger.warning(f"Failed to register failed vacancy job: {reg_error}")

        return {
            "status": "error",
            "company_id": company_id,
            "error": error_msg,
        }


def send_vacancy_analytics_data() -> Dict[str, Any]:
    """
    RQ task to enqueue individual vacancy analytics jobs for each active company.
    Creates a separate job per company to ensure data isolation.
    Runs on the same 4-hour schedule as company analytics.

    Returns:
        Dictionary with enqueue results
    """
    import django_rq

    failed_company_ids = []

    try:
        company_ids = HRAnalyticsService.get_company_ids()

        if not company_ids:
            logger.info("No active companies found for vacancy analytics")
            return {
                "status": "completed",
                "companies_processed": 0,
                "message": "No active companies found",
            }

        logger.info(
            f"Enqueuing vacancy analytics jobs for {len(company_ids)} companies"
        )

        queue = django_rq.get_queue("default")

        jobs_enqueued = 0
        for company_id in company_ids:
            try:
                queue.enqueue(
                    send_single_company_vacancy_analytics,
                    str(company_id),
                    job_timeout="5m",
                    meta={"company_id": str(company_id), "task": "vacancy_analytics"},
                )
                jobs_enqueued += 1
                logger.debug(
                    f"Enqueued vacancy analytics job for company {company_id}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to enqueue vacancy analytics job for company {company_id}: {e}"
                )
                failed_company_ids.append(company_id)

        logger.info(
            f"Successfully enqueued {jobs_enqueued} company vacancy analytics jobs"
        )

        return {
            "status": "completed",
            "companies_processed": len(company_ids),
            "jobs_enqueued": jobs_enqueued,
            "failed_company_ids": failed_company_ids,
        }

    except Exception as e:
        logger.exception(f"Failed to enqueue company vacancy analytics jobs: {e}")
        return {
            "status": "error",
            "error": str(e),
            "failed_company_ids": failed_company_ids,
        }


# =============================================================================
# Recruiter Applications Summary Email Task
# =============================================================================

def send_recruiter_applications_summary() -> Dict[str, Any]:
    """
    RQ task: Send recruiters a digest email of new applications every 4 hours.

    This task:
    1. Queries all applications with status="APPLIED" that haven't been notified yet
    2. Groups applications by recruiter (via vacancy.created_by)
    3. For each recruiter with new applications, sends a summary email
    4. Records which applications were notified to prevent duplicates

    Returns:
        Dictionary with task execution status and statistics
    """
    import django_rq
    from collections import defaultdict

    from apps.applications.models import JobApplication
    from apps.applications.models.choices import ApplicationStatus
    from apps.general.models import ApplicationSummaryNotification

    logger.info("[APPLICATIONS_SUMMARY] Starting recruiter applications summary task")

    period_hours = 4  # For display in email template

    try:
        # Query applications with status APPLIED that haven't been notified yet
        # Exclude applications that already have a notification record
        applications = (
            JobApplication.objects
            .filter(
                status=ApplicationStatus.APPLIED,
            )
            .exclude(
                # Exclude applications that have already been notified
                id__in=ApplicationSummaryNotification.objects.values_list(
                    "application_id", flat=True
                )
            )
            .select_related(
                "candidate",
                "candidate__candidateprofile",
                "vacancy",
                "vacancy__created_by",
            )
            .prefetch_related(
                "vacancy__created_by__recruiterprofile_set"
            )
            .order_by("vacancy__created_by", "vacancy", "-applied_at")
        )

        total_applications = applications.count()
        logger.info(
            f"[APPLICATIONS_SUMMARY] Found {total_applications} new applications "
            f"not yet notified"
        )

        if total_applications == 0:
            logger.info("[APPLICATIONS_SUMMARY] No new applications. Skipping email sending.")
            return {
                "status": "completed",
                "message": "No new applications to notify",
                "applications_found": 0,
                "emails_sent": 0,
            }

        # Group applications by recruiter
        recruiter_applications = defaultdict(list)
        for app in applications:
            recruiter = app.vacancy.created_by
            if recruiter:
                recruiter_applications[recruiter].append(app)

        logger.info(
            f"[APPLICATIONS_SUMMARY] Grouped applications for {len(recruiter_applications)} recruiters"
        )

        # Get the default queue and enqueue individual email tasks
        queue = django_rq.get_queue("default")
        emails_enqueued = 0
        failed_recruiters = []

        for recruiter, apps in recruiter_applications.items():
            try:
                queue.enqueue(
                    _send_single_recruiter_applications_email,
                    str(recruiter.id),
                    [str(app.id) for app in apps],
                    period_hours,
                    job_timeout="2m",
                    meta={"recruiter_id": str(recruiter.id), "task": "applications_summary"},
                )
                emails_enqueued += 1
                logger.debug(
                    f"[APPLICATIONS_SUMMARY] Enqueued email task for recruiter {recruiter.id} "
                    f"with {len(apps)} applications"
                )
            except Exception as e:
                logger.warning(
                    f"[APPLICATIONS_SUMMARY] Failed to enqueue email for recruiter {recruiter.id}: {e}"
                )
                failed_recruiters.append(str(recruiter.id))

        logger.info(
            f"[APPLICATIONS_SUMMARY] Successfully enqueued {emails_enqueued} email tasks"
        )

        return {
            "status": "completed",
            "applications_found": total_applications,
            "recruiters_processed": len(recruiter_applications),
            "emails_enqueued": emails_enqueued,
            "failed_recruiters": failed_recruiters,
        }

    except Exception as e:
        logger.exception(f"[APPLICATIONS_SUMMARY] Failed to process applications summary: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


def _send_single_recruiter_applications_email(
    recruiter_id: str,
    application_ids: List[str],
    period_hours: int = 4,
) -> Dict[str, Any]:
    """
    RQ worker task: Send applications summary email to a single recruiter.

    After successfully sending the email, records the notification in the database
    to prevent duplicate notifications for the same applications.

    Args:
        recruiter_id: UUID string of the recruiter
        application_ids: List of application UUID strings
        period_hours: Number of hours in the summary period (for display)

    Returns:
        Dictionary with send status
    """
    from uuid import UUID

    from django.conf import settings as django_settings
    from django.utils import timezone as dj_timezone

    from apps.applications.models import JobApplication
    from apps.authentication.models import Recruiter
    from apps.general.models import ApplicationSummaryNotification
    from apps.general.services.base_email_service import BaseEmailService
    from apps.general.services.language_cache import LanguageCacheService

    logger.info(
        f"[APPLICATIONS_SUMMARY] Processing email for recruiter {recruiter_id} "
        f"with {len(application_ids)} applications"
    )

    try:
        recruiter_uuid = UUID(recruiter_id)

        # Get recruiter
        recruiter = Recruiter.objects.select_related().prefetch_related(
            "recruiterprofile_set"
        ).get(id=recruiter_uuid)

        # Get recruiter profile for full name
        recruiter_profile = recruiter.recruiterprofile_set.first()
        recruiter_name = (
            recruiter_profile.full_name if recruiter_profile and recruiter_profile.full_name
            else "Recruiter"
        )

        # Get recruiter's preferred language from cache
        language = LanguageCacheService.get_user_language(recruiter_id)

        # Get applications that haven't been notified yet (double-check)
        application_uuids = [UUID(app_id) for app_id in application_ids]
        already_notified = set(
            ApplicationSummaryNotification.objects.filter(
                application_id__in=application_uuids,
                recruiter_id=recruiter_uuid,
            ).values_list("application_id", flat=True)
        )

        applications = JobApplication.objects.filter(
            id__in=application_uuids
        ).exclude(
            id__in=already_notified
        ).select_related(
            "candidate",
            "candidate__candidateprofile",
            "vacancy",
        )

        if not applications.exists():
            logger.info(
                f"[APPLICATIONS_SUMMARY] All applications already notified for recruiter {recruiter_id}"
            )
            return {
                "status": "skipped",
                "recruiter_id": recruiter_id,
                "reason": "All applications already notified",
            }

        # Build frontend URLs
        frontend_url = getattr(django_settings, "FRONTEND_URL", "https://workxplorer.uz")
        dashboard_url = f"{frontend_url}/dashboard/vacancies/active"

        # Build applications context
        applications_list = list(applications)
        applications_context = []
        for app in applications_list:
            candidate_profile = getattr(app.candidate, "candidateprofile", None)
            applications_context.append({
                "vacancy_title": app.vacancy.title,
                "vacancy_url": f"{frontend_url}/vacancies/{app.vacancy.id}",
                "candidate_name": candidate_profile.full_name if candidate_profile else "N/A",
                "candidate_email": app.candidate.email,
                "candidate_phone": candidate_profile.phone if candidate_profile and candidate_profile.phone else "-",
            })

        # Build email context
        context = {
            "recruiter_name": recruiter_name,
            "applications": applications_context,
            "total_count": len(applications_context),
            "period_hours": period_hours,
            "dashboard_url": dashboard_url,
        }

        # Get and render template
        template = BaseEmailService.get_email_template("applications-summary", language)
        if not template:
            logger.error(
                f"[APPLICATIONS_SUMMARY] No template found for type='applications-summary' "
                f"language='{language}'"
            )
            return {
                "status": "error",
                "recruiter_id": recruiter_id,
                "error": "Template not found",
            }

        subject, body = BaseEmailService.render_template(template, context)

        # Send email
        BaseEmailService.send_email(
            to_email=recruiter.email,
            subject=subject,
            body=body,
        )

        # Record notifications to prevent duplicates
        now = dj_timezone.now()
        notifications_to_create = [
            ApplicationSummaryNotification(
                application_id=app.id,
                recruiter_id=recruiter_uuid,
                notified_at=now,
            )
            for app in applications_list
        ]
        ApplicationSummaryNotification.objects.bulk_create(
            notifications_to_create,
            ignore_conflicts=True,  # In case of race conditions
        )

        logger.info(
            f"[APPLICATIONS_SUMMARY] Successfully sent email to recruiter {recruiter_id} "
            f"({recruiter.email}) with {len(applications_context)} applications. "
            f"Recorded {len(notifications_to_create)} notification(s)."
        )

        return {
            "status": "success",
            "recruiter_id": recruiter_id,
            "email": recruiter.email,
            "applications_count": len(applications_context),
            "language": language,
        }

    except Recruiter.DoesNotExist:
        logger.error(f"[APPLICATIONS_SUMMARY] Recruiter {recruiter_id} not found")
        return {
            "status": "error",
            "recruiter_id": recruiter_id,
            "error": "Recruiter not found",
        }
    except Exception as e:
        logger.exception(
            f"[APPLICATIONS_SUMMARY] Failed to send email to recruiter {recruiter_id}: {e}"
        )
        return {
            "status": "error",
            "recruiter_id": recruiter_id,
            "error": str(e),
        }
