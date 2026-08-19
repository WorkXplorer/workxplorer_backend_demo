"""
Data processing functions for HR analytics.
Handles preparation and serialization of application, resume, and vacancy data.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils import timezone
from django.core.exceptions import FieldDoesNotExist

from apps.resumes.models import Resume
from apps.vacancies.models import Vacancy
from apps.applications.models import JobApplication as Application
from .utils import serialize_value, base_instance_dict
from .cards import (
    calculate_applications_count,
    calculate_vacancy_views,
    calculate_average_view_time,
)

logger = logging.getLogger(__name__)


def get_recent_applications(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get applications from the last `hours` hours with candidate and vacancy details.
    Returns a list of dictionaries with serialized data suitable for JSON.
    """
    cutoff_time = timezone.now() - timedelta(hours=hours)

    # Optimize with select_related to avoid N+1 queries
    applications = (
        Application.objects.filter(applied_at__gte=cutoff_time)
        .select_related("candidate", "vacancy")
        .order_by("-applied_at")
    )

    result = []
    for app in applications:
        app_data = base_instance_dict(app, ["status", "cover_letter"])

        # Add candidate info
        if app.candidate:
            candidate_data = base_instance_dict(
                app.candidate, ["first_name", "last_name", "email"]
            )
            app_data["candidate"] = candidate_data

        # Add vacancy info
        if app.vacancy:
            vacancy_data = base_instance_dict(
                app.vacancy, ["title", "company_name"]
            )
            app_data["vacancy"] = vacancy_data

        result.append(app_data)

    logger.info(
        "Retrieved %d recent applications from last %d hours", len(result), hours
    )
    return result


def get_recent_resumes(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get resumes created/updated in the last `hours` hours.
    Returns a list of dictionaries with serialized data.
    """
    cutoff_time = timezone.now() - timedelta(hours=hours)

    # Get resumes created or updated recently
    resumes = (
        Resume.objects.filter(
            models.Q(created_at__gte=cutoff_time)
            | models.Q(updated_at__gte=cutoff_time)
        )
        .select_related("candidate")
        .order_by("-updated_at")
    )

    result = []
    for resume in resumes:
        resume_data = base_instance_dict(
            resume, ["title", "summary", "experience_level"]
        )

        # Add candidate info
        if resume.candidate:
            candidate_data = base_instance_dict(
                resume.candidate, ["first_name", "last_name", "email"]
            )
            resume_data["candidate"] = candidate_data

        result.append(resume_data)

    logger.info("Retrieved %d recent resumes from last %d hours", len(result), hours)
    return result


def get_recent_vacancies(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get vacancies created/updated in the last `hours` hours.
    Returns a list of dictionaries with serialized data.
    """
    cutoff_time = timezone.now() - timedelta(hours=hours)

    vacancies = Vacancy.objects.filter(
        models.Q(created_at__gte=cutoff_time) | models.Q(updated_at__gte=cutoff_time)
    ).order_by("-updated_at")

    result = []
    for vacancy in vacancies:
        vacancy_data = base_instance_dict(
            vacancy,
            [
                "title",
                "company_name",
                "salary_min",
                "salary_max",
                "employment_type",
                "is_active",
            ],
        )
        result.append(vacancy_data)

    logger.info("Retrieved %d recent vacancies from last %d hours", len(result), hours)
    return result


def get_applications_data(qs: Optional[models.QuerySet] = None) -> List[Dict[str, Any]]:
    """
    Retrieve application data and return a list of JSON-serializable dicts.
    If qs is None, all Application objects are used.
    """
    if qs is None:
        qs = Application.objects.all()

    # Build select_related only for actual forward relations to avoid errors
    select_related_fields = []
    for name in ("candidate", "vacancy", "resume_used", "last_updated_by"):
        try:
            f = Application._meta.get_field(name)
            if getattr(f, "is_relation", False) and not getattr(
                    f, "many_to_many", False
            ):
                select_related_fields.append(name)
        except FieldDoesNotExist:
            continue

    if select_related_fields:
        qs = qs.select_related(*select_related_fields)

    results = []
    for inst in qs:
        try:
            data = base_instance_dict(
                inst, extra_fields=["status", "cover_letter", "applied_at", "hired_at"]
            )
            # Related objects (conditional)
            if hasattr(inst, "candidate") and inst.candidate is not None:
                data["candidate"] = base_instance_dict(
                    inst.candidate, extra_fields=["first_name", "last_name", "email"]
                )
            # recruiter / last_updated_by compatibility
            if hasattr(inst, "recruiter") and inst.recruiter is not None:
                data["recruiter"] = base_instance_dict(
                    inst.recruiter, extra_fields=["first_name", "last_name", "email"]
                )
            elif hasattr(inst, "last_updated_by") and inst.last_updated_by is not None:
                data["last_updated_by"] = base_instance_dict(
                    inst.last_updated_by,
                    extra_fields=["first_name", "last_name", "email"],
                )
            if hasattr(inst, "vacancy") and inst.vacancy is not None:
                data["vacancy"] = base_instance_dict(
                    inst.vacancy,
                    extra_fields=["title", "salary_min", "salary_max", "company_name"],
                )
            # resume_used compatibility
            if hasattr(inst, "resume") and inst.resume is not None:
                data["resume"] = base_instance_dict(
                    inst.resume, extra_fields=["summary"]
                )
            elif hasattr(inst, "resume_used") and inst.resume_used is not None:
                data["resume_used"] = base_instance_dict(
                    inst.resume_used, extra_fields=["summary"]
                )
            results.append(data)
        except Exception:
            logger.exception(
                "Error serializing Application id=%s", getattr(inst, "id", None)
            )
    return results


def get_resumes_data(qs: Optional[models.QuerySet] = None) -> List[Dict[str, Any]]:
    """
    Retrieve resume data and return a list of JSON-serializable dicts.
    If qs is None, all Resume objects are used.
    """
    if qs is None:
        qs = Resume.objects.all()

    # Prefetch skills if this relation exists on Resume
    m2m_fields = [
        f.name for f in Resume._meta.get_fields() if getattr(f, "many_to_many", False)
    ]
    if "skills" in m2m_fields:
        qs = qs.prefetch_related("skills")

    results = []
    for inst in qs:
        try:
            data = base_instance_dict(
                inst, extra_fields=["title", "summary", "education", "experience_years"]
            )
            # Candidate/user info
            if hasattr(inst, "candidate") and inst.candidate is not None:
                data["candidate"] = base_instance_dict(
                    inst.candidate, extra_fields=["first_name", "last_name", "email"]
                )
            # Skills
            if hasattr(inst, "skills"):
                try:
                    skills = [
                        s.name if hasattr(s, "name") else serialize_value(s)
                        for s in getattr(inst, "skills").all()
                    ]
                    data["skills"] = skills
                except Exception:
                    # fallback: maybe skills is a list
                    data["skills"] = serialize_value(getattr(inst, "skills"))
            results.append(data)
        except Exception:
            logger.exception(
                "Error serializing Resume id=%s", getattr(inst, "id", None)
            )
    return results


def get_vacancies_data(qs: Optional[models.QuerySet] = None) -> List[Dict[str, Any]]:
    """
    Retrieve vacancy data and return a list of JSON-serializable dicts.
    If qs is None, all Vacancy objects are used.
    """
    if qs is None:
        qs = Vacancy.objects.all()

    # Prefetch relations commonly on Vacancy
    relation_names = [f.name for f in Vacancy._meta.get_fields()]
    prefetch = []
    if "skills" in relation_names:
        prefetch.append("skills")
    if "company" in relation_names:
        qs = qs.select_related("company")
    if prefetch:
        qs = qs.prefetch_related(*prefetch)

    results = []
    for inst in qs:
        try:
            data = base_instance_dict(
                inst,
                extra_fields=[
                    "title",
                    "responsibilities",
                    "requirements",
                    "salary_min",
                    "salary_max",
                    "salary_currency",
                    "employment_type",
                    "employment_format",
                    "experience",
                    "number_of_positions",
                    "contact_email",
                    "contact_phone",
                    "about_us",
                    "additional_info",
                    "is_active",
                ],
            )
            if hasattr(inst, "company") and inst.company is not None:
                data["company"] = base_instance_dict(
                    inst.company, extra_fields=["name", "description", "industry"]
                )
            if hasattr(inst, "domain") and inst.domain is not None:
                data["domain"] = base_instance_dict(
                    inst.domain, extra_fields=["name", "description"]
                )
            if hasattr(inst, "required_skills"):
                try:
                    # Handle ManyToMany relationship for required_skills
                    skills = [
                        s.name if hasattr(s, "name") else serialize_value(s)
                        for s in getattr(inst, "required_skills").all()
                    ]
                    data["required_skills"] = skills
                except Exception:
                    data["required_skills"] = serialize_value(
                        getattr(inst, "required_skills")
                    )

            # Add average view time calculation if method exists
            if hasattr(inst, "calculate_average_view_time"):
                try:
                    data["average_view_time"] = serialize_value(
                        inst.calculate_average_view_time()
                    )
                except Exception:
                    logger.exception(
                        "Error calculating average view time for Vacancy id=%s",
                        getattr(inst, "id", None),
                    )
                    data["average_view_time"] = None

            results.append(data)
        except Exception:
            logger.exception(
                "Error serializing Vacancy id=%s", getattr(inst, "id", None)
            )
    return results


def prepare_summary_data() -> Dict[str, Any]:
    """
    Prepare a comprehensive summary of recent activities and metrics.
    This is the main data preparation function for HR webhooks.
    """
    now = timezone.now()

    # Get recent data (last 24 hours)
    recent_applications = get_recent_applications(24)
    recent_resumes = get_recent_resumes(24)
    recent_vacancies = get_recent_vacancies(24)

    # Calculate metrics for the last 7 days vs previous 7 days
    application_metrics = calculate_applications_count(period_days=7)
    view_metrics = calculate_vacancy_views(period_days=7)

    # Calculate average view time for the last 7 days
    week_ago = now - timedelta(days=7)
    avg_view_time = calculate_average_view_time(week_ago, now)

    # Prepare the summary payload
    summary = {
        "timestamp": serialize_value(now),
        "data_period": {"recent_data_hours": 24, "metrics_period_days": 7},
        "counts": {
            "recent_applications": len(recent_applications),
            "recent_resumes": len(recent_resumes),
            "recent_vacancies": len(recent_vacancies),
        },
        "metrics": {
            "applications": application_metrics,
            "views": view_metrics,
            "average_view_time": avg_view_time,
        },
        "recent_data": {
            "applications": recent_applications,
            "resumes": recent_resumes,
            "vacancies": recent_vacancies,
        },
    }

    logger.info(
        "Prepared summary data: %d applications, %d resumes, %d vacancies",
        len(recent_applications),
        len(recent_resumes),
        len(recent_vacancies),
    )

    return summary
