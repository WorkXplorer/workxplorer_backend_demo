"""
Statistics cards analytics for EduPartner analytics data.
Handles the calculation of 9 dashboard card metrics.
"""

from datetime import timedelta
from django.db.models import Exists, OuterRef, Avg, Q
from django.utils import timezone

from apps.applications.models import (
    ApplicationStatusModel,
    JobApplication as Application,
    StatusCategory,
)
from apps.vacancies.models import Vacancy
from apps.authentication.models import Candidate
from apps.authentication.transitions import CREATE_PROFILE, CREATE_RESUME, VACANCY_APPLY, VERIFY_VAULT
from apps.student_analytics.models import StudentAnalytics
from apps.resumes.models import Resume
from apps.resumes.models.choices import WorkStatus


def get_statistics_cards(
    candidate_ids: list,
    faculty_domain_ids: list,
    edupartner_id: str = None,
) -> dict:
    total = len(candidate_ids)

    # 1. From source — all candidates across the whole edupartner
    source_students = _count_source_students(edupartner_id)

    # 2. Registered — candidates in this faculty (total)
    registered = total

    # 3. Active in last 30 days
    active_30_days = _count_active_30_days(candidate_ids)

    # 4. Resume uploaded
    resume_uploaded = _count_resume_uploaded(candidate_ids)

    # 5. Profile filled — 100% onboarding completed
    profile_filled = _count_profile_filled(candidate_ids)

    # 6. Assessment passed — have StudentAnalytics (career path)
    assessment_passed = _count_assessment_passed(candidate_ids)

    # 7. Average graduate salary
    average_graduate_salary = _calculate_avg_graduate_salary(candidate_ids)

    # 8. Students on internships
    students_on_internships = _count_internships(candidate_ids)

    # 9. Total vacancies offered
    total_vacancies_offered = _count_vacancies(faculty_domain_ids)

    return {
        "source_students": source_students,
        "registered": registered,
        "active_30_days": active_30_days,
        "resume_uploaded": resume_uploaded,
        "profile_filled": profile_filled,
        "assessment_passed": assessment_passed,
        "average_graduate_salary": average_graduate_salary,
        "students_on_internships": students_on_internships,
        "total_vacancies": total_vacancies_offered,
    }


def _count_source_students(edupartner_id: str) -> int:
    if not edupartner_id:
        return 0
    return Candidate.objects.filter(edupartner_id=edupartner_id).count()


def _count_active_30_days(candidate_ids: list) -> int:
    """Count candidates who logged in within the last 30 days."""
    if not candidate_ids:
        return 0
    thirty_days_ago = timezone.now() - timedelta(days=30)
    return Candidate.objects.filter(
        id__in=candidate_ids,
        last_login__gte=thirty_days_ago,
    ).count()


def _count_resume_uploaded(candidate_ids: list) -> int:
    if not candidate_ids:
        return 0
    return Resume.objects.filter(
        candidate_id__in=candidate_ids,
        is_active=True,
    ).values("candidate_id").distinct().count()


def _count_profile_filled(candidate_ids: list) -> int:
    """Count candidates with 100% onboarding completed (all 4 steps in JSONB)."""
    if not candidate_ids:
        return 0
    return Candidate.objects.filter(
        id__in=candidate_ids,
    ).filter(
        Q(onboarding_progress__has_key=CREATE_PROFILE)
        & Q(onboarding_progress__has_key=CREATE_RESUME)
        & Q(onboarding_progress__has_key=VACANCY_APPLY)
        & Q(onboarding_progress__has_key=VERIFY_VAULT)
    ).count()


def _count_assessment_passed(candidate_ids: list) -> int:
    if not candidate_ids:
        return 0
    return StudentAnalytics.objects.filter(
        candidate_id__in=candidate_ids,
    ).count()


def _calculate_avg_graduate_salary(candidate_ids: list) -> float:
    if not candidate_ids:
        return 0.0
    employed_statuses = WorkStatus.employed_statuses()
    result = Resume.objects.filter(
        candidate_id__in=candidate_ids,
        is_active=True,
        work_status__in=employed_statuses,
        current_salary__isnull=False,
    ).aggregate(avg=Avg("current_salary"))
    return float(result["avg"] or 0)


def _count_internships(candidate_ids: list) -> int:
    if not candidate_ids:
        return 0
    hired_status_subquery = ApplicationStatusModel.objects.filter(
        company_id=OuterRef("vacancy__company_id"),
        key=OuterRef("status"),
        category__key=StatusCategory.HIRED,
        is_active=True,
    )
    return (
        Application.objects.filter(
            candidate_id__in=candidate_ids,
            vacancy__employment_type="INTERNSHIP",
            is_active=True,
        )
        .annotate(is_hired_status=Exists(hired_status_subquery))
        .filter(is_hired_status=True)
        .count()
    )


def _count_vacancies(faculty_domain_ids: list) -> int:
    if not faculty_domain_ids:
        return 0
    return Vacancy.objects.filter(
        domain_id__in=faculty_domain_ids,
        is_active=True,
    ).count()
