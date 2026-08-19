"""
RQ tasks for sending edupartner analytics data to the external service.
Uses protobuf encoding for efficient binary transmission.
"""

import logging
import requests
from datetime import date
from django.conf import settings
from uuid import UUID

from apps.edupartners.services.analytics import EduPartnerAnalyticsService
from apps.edupartners.services.protobuf_service import (
    EduPartnerAnalyticsProtobufService,
    extract_domain_name,
)

logger = logging.getLogger(__name__)


# External edupartner analytics endpoint
EDUPARTNER_ANALYTICS_URL = getattr(
    settings,
    "EDUPARTNER_ANALYTICS_WEBHOOK_URL",
    "https://edupartner-service.workxplorer.uz/api/analytics",
)


def _get_job_queue_service():
    """Lazy import to avoid circular imports."""
    from apps.general.services.job_queue_service import JobQueueService
    return JobQueueService


def _get_job_queue_model():
    """Lazy import to avoid circular imports."""
    from apps.general.models import JobQueue
    return JobQueue


def send_single_faculty_analytics(faculty_id: str, job_queue_id: str = None):
    """
    RQ task to collect and send analytics for a single faculty.
    This ensures each faculty only receives their own statistics.

    Args:
        faculty_id: UUID string of the faculty
        job_queue_id: Optional UUID string of the JobQueue record for tracking
    """
    JobQueueService = _get_job_queue_service()
    JobQueue = _get_job_queue_model()
    job = None

    try:
        # Convert string to UUID if needed
        if isinstance(faculty_id, str):
            faculty_id_uuid = UUID(faculty_id)
        else:
            faculty_id_uuid = faculty_id
            faculty_id = str(faculty_id)

        # Collect analytics for this specific faculty
        analytics_data = EduPartnerAnalyticsService.get_faculty_analytics(faculty_id_uuid)

        if not analytics_data:
            logger.warning(f"No analytics data for faculty {faculty_id}")
            return

        # Get faculty name for job registration
        faculty_name = analytics_data.get("faculty", {}).get("name", "Unknown")

        # Use existing JobQueue record if job_queue_id is provided; otherwise register a new job
        if job_queue_id:
            try:
                job = JobQueue.objects.get(id=job_queue_id)
            except JobQueue.DoesNotExist:
                job = JobQueueService.register_job(
                    job_type=JobQueue.JobType.EDU_ANALYTICS,
                    target_date=date.today(),
                    target_id=faculty_id,
                    target_name=faculty_name,
                    payload=analytics_data,
                )
                logger.warning(
                    "JobQueue with id %s does not exist; proceeding with newly registered job %s",
                    job_queue_id,
                    getattr(job, "id", None),
                )
        else:
            job = JobQueueService.register_job(
                job_type=JobQueue.JobType.EDU_ANALYTICS,
                target_date=date.today(),
                target_id=faculty_id,
                target_name=faculty_name,
                payload=analytics_data,
            )

        # Mark job as processing
        job.mark_processing()

        # Send data to external edupartner service
        _send_analytics_to_service(analytics_data)

        # Mark job as completed
        job.mark_completed()

        logger.info(
            f"Successfully sent analytics for faculty: "
            f"{faculty_name} from {analytics_data['edupartner']['name']} (faculty_id={faculty_id})"
        )

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Failed to send analytics for faculty {faculty_id}: {e}")

        # Mark job as failed if we have a job record
        if job:
            job.mark_failed(error_msg)
        else:
            # Create a failed job record for tracking
            try:
                job = JobQueueService.register_job(
                    job_type=JobQueue.JobType.EDU_ANALYTICS,
                    target_date=date.today(),
                    target_id=faculty_id,
                    target_name=None,
                )
                job.mark_failed(error_msg)
            except Exception as reg_error:
                logger.warning(f"Failed to register failed job: {reg_error}")

        raise


def send_edupartner_level_analytics(edupartner_id: str, job_queue_id: str = None):
    """
    RQ task to collect and send analytics for an edupartner that has candidates
    but no active faculties (invisible to the per-faculty sync).

    Args:
        edupartner_id: UUID string of the edupartner
        job_queue_id: Optional UUID string of the JobQueue record for tracking
    """
    JobQueueService = _get_job_queue_service()
    JobQueue = _get_job_queue_model()
    job = None

    try:
        if isinstance(edupartner_id, str):
            edupartner_id_uuid = UUID(edupartner_id)
        else:
            edupartner_id_uuid = edupartner_id
            edupartner_id = str(edupartner_id)

        analytics_data = EduPartnerAnalyticsService.get_edupartner_analytics(edupartner_id_uuid)

        if not analytics_data:
            logger.warning(f"No analytics data for edupartner {edupartner_id}")
            return

        edupartner_name = analytics_data.get("edupartner", {}).get("name", "Unknown")

        if job_queue_id:
            try:
                job = JobQueue.objects.get(id=job_queue_id)
            except JobQueue.DoesNotExist:
                job = JobQueueService.register_job(
                    job_type=JobQueue.JobType.EDU_ANALYTICS,
                    target_date=date.today(),
                    target_id=edupartner_id,
                    target_name=edupartner_name,
                    payload=analytics_data,
                )
                logger.warning(
                    "JobQueue with id %s does not exist; proceeding with newly registered job %s",
                    job_queue_id,
                    getattr(job, "id", None),
                )
        else:
            job = JobQueueService.register_job(
                job_type=JobQueue.JobType.EDU_ANALYTICS,
                target_date=date.today(),
                target_id=edupartner_id,
                target_name=edupartner_name,
                payload=analytics_data,
            )

        job.mark_processing()

        _send_analytics_to_service(analytics_data)

        job.mark_completed()

        logger.info(
            f"Successfully sent edupartner-level analytics for: "
            f"{edupartner_name} (edupartner_id={edupartner_id}, no active faculties)"
        )

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Failed to send edupartner-level analytics for {edupartner_id}: {e}")

        if job:
            job.mark_failed(error_msg)
        else:
            try:
                job = JobQueueService.register_job(
                    job_type=JobQueue.JobType.EDU_ANALYTICS,
                    target_date=date.today(),
                    target_id=edupartner_id,
                    target_name=None,
                )
                job.mark_failed(error_msg)
            except Exception as reg_error:
                logger.warning(f"Failed to register failed job: {reg_error}")

        raise


def send_edupartner_analytics_data():
    """
    RQ task to enqueue individual analytics jobs for each faculty, plus one
    edupartner-level job for each edupartner that has candidates but no
    active faculties (otherwise permanently invisible to the sync).
    """
    import django_rq

    try:
        # Get all active faculty IDs
        faculty_ids = EduPartnerAnalyticsService.get_faculty_ids()
        faculty_less_edupartner_ids = EduPartnerAnalyticsService.get_faculty_less_edupartner_ids()

        if not faculty_ids and not faculty_less_edupartner_ids:
            logger.info("No active faculties or faculty-less edupartners found")
            return

        logger.info(
            f"Enqueuing analytics jobs for {len(faculty_ids)} faculties and "
            f"{len(faculty_less_edupartner_ids)} faculty-less edupartners"
        )

        # Get the default queue
        queue = django_rq.get_queue("default")

        # Enqueue a separate job for each faculty
        for faculty_id in faculty_ids:
            queue.enqueue(
                send_single_faculty_analytics,
                str(faculty_id),
                job_timeout="5m",
                meta={"faculty_id": str(faculty_id)},
            )
            logger.debug(f"Enqueued analytics job for faculty {faculty_id}")

        # Enqueue a separate job for each faculty-less edupartner
        for edupartner_id in faculty_less_edupartner_ids:
            queue.enqueue(
                send_edupartner_level_analytics,
                str(edupartner_id),
                job_timeout="5m",
                meta={"edupartner_id": str(edupartner_id)},
            )
            logger.debug(f"Enqueued edupartner-level analytics job for edupartner {edupartner_id}")

        logger.info(
            f"Successfully enqueued {len(faculty_ids)} faculty analytics jobs and "
            f"{len(faculty_less_edupartner_ids)} edupartner-level analytics jobs"
        )

    except Exception as e:
        logger.exception(f"Failed to enqueue faculty analytics jobs: {e}")
        raise


def _send_analytics_to_service(analytics_data: dict):
    """
    Send analytics data to the external edupartner service using protobuf encoding.

    Args:
        analytics_data: Dictionary containing analytics for a single edupartner
    """
    try:
        # Validate that all required keys are present.
        # "faculty" is intentionally not required: edupartner-level analytics
        # (for edupartners with candidates but no active faculties) has no
        # faculty scope, and the payload building below already defaults
        # faculty fields to empty values when "faculty" is absent.
        required_keys = [
            "statistics", "popular_industries", "employed_graduates",
            "hiring_funnel", "top_companies_by_placements", "timestamp",
            "edupartner"
        ]
        missing_keys = [key for key in required_keys if key not in analytics_data]
        if missing_keys:
            logger.error(f"Missing required keys in analytics data: {missing_keys}")
            raise ValueError(f"Missing required keys: {missing_keys}")

        # Safely extract faculty data
        faculty_data = analytics_data.get("faculty") or {}
        domain_data = faculty_data.get("domain")

        # Use shared utility function for domain extraction
        faculty_domain = extract_domain_name(domain_data)
        faculty_domain_id = ""
        if isinstance(domain_data, dict) and domain_data.get("id"):
            faculty_domain_id = str(domain_data["id"])

        # Prepare payload for the 9 cards and popular industries chart
        stats = analytics_data["statistics"]
        payload = {
            "edupartner_id": str(analytics_data["edupartner"]["id"]) if analytics_data.get("edupartner", {}).get(
                "id") else "",
            "edupartner_name": analytics_data.get("edupartner", {}).get("name") or "",
            "faculty_id": str(faculty_data.get("id")) if faculty_data.get("id") else "",
            "faculty_name": faculty_data.get("name") or "",
            "faculty_domain": faculty_domain,
            "faculty_domain_id": faculty_domain_id,
            "cards": {
                "source_students": {
                    "value": stats["source_students"],
                    "label": "Из источника",
                },
                "registered": {
                    "value": stats["registered"],
                    "label": "Зарегистрировано",
                },
                "active_30_days": {
                    "value": stats["active_30_days"],
                    "label": "Активные 30 дней",
                },
                "resume_uploaded": {
                    "value": stats["resume_uploaded"],
                    "label": "Резюме загружено",
                },
                "profile_filled": {
                    "value": stats["profile_filled"],
                    "label": "Профиль заполнен",
                },
                "assessment_passed": {
                    "value": stats["assessment_passed"],
                    "label": "Assessment пройден",
                },
                "graduate_salary": {
                    "value": stats["average_graduate_salary"],
                    "currency": "UZS",
                    "label": "Ср. зарплата выпускников",
                },
                "students_on_internships": {
                    "value": stats["students_on_internships"],
                    "label": "Кол-во студентов на стажировках",
                },
                "total_vacancies": {
                    "value": stats["total_vacancies"],
                    "label": "Всего вакансий",
                },
            },
            # Popular Industries chart data
            "popular_industries": analytics_data["popular_industries"],
            "employed_graduates": analytics_data["employed_graduates"],
            # Hiring Funnel chart data
            "hiring_funnel": analytics_data["hiring_funnel"],
            # Top Companies by Student Placements chart data
            "top_companies_by_placements": analytics_data[
                "top_companies_by_placements"
            ],
            # Timestamp
            "timestamp": analytics_data["timestamp"],
        }

        # Validate data before encoding
        if not EduPartnerAnalyticsProtobufService.validate_analytics_data(payload):
            logger.error("Analytics data validation failed, aborting send.")
            raise ValueError("Invalid analytics data payload; aborting protobuf encoding.")

        # Encode data using PURE protobuf
        protobuf_data = EduPartnerAnalyticsProtobufService.encode_analytics_data(payload)
        # Log encoding efficiency
        encoding_info = EduPartnerAnalyticsProtobufService.get_encoding_info(payload)

        # Check if encoding_info contains an error
        if 'error' in encoding_info:
            logger.warning(
                f"Failed to calculate encoding info: {encoding_info['error']}. "
                f"Continuing with data transmission."
            )
        else:
            logger.info(
                f"PURE protobuf encoding: {encoding_info.get('efficiency_gain', 'N/A')} "
                f"({encoding_info.get('json_size_bytes', 0)} -> {encoding_info.get('protobuf_size_bytes', 0)} bytes) "
                f"Format: {encoding_info.get('format', 'Unknown')}"
            )

        # Send to external service with protobuf content
        service_key = getattr(settings, "EDUPARTNER_SERVICE_KEY", "")
        if not service_key:
            raise ValueError("EDUPARTNER_SERVICE_KEY is not configured")

        response = requests.post(
            EDUPARTNER_ANALYTICS_URL,
            data=protobuf_data,
            headers={
                "Content-Type": "application/x-protobuf",
                "Content-Encoding": "protobuf",
                "X-Data-Format": "workxplorer-protobuf-v4",
                "X-SERVICE-KEY": service_key,
            },
            timeout=30,
        )

        response.raise_for_status()

        logger.info(
            f"PURE protobuf analytics sent successfully for {analytics_data['edupartner']['name']} "
            f"(size: {len(protobuf_data)} bytes, format: Pure Protobuf Binary v4)"
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send protobuf analytics to edupartner service: {e}")
        # Re-raise to trigger RQ retry mechanism
        raise
