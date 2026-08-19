from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext as _
from apps.resumes.models import Resume
from apps.applications.models import JobApplication, ApplicationStatusModel, StatusCategory
from apps.authentication.transitions import get_candidate_progress


class StudentDetailSerializer(serializers.Serializer):
    """
    Nested serializer for student detail — 5 sections.
    ponytail: prefetches all status labels upfront to avoid per-application N+1 queries.
    """

    def to_representation(self, instance):
        candidate = instance.candidate
        now = timezone.now()
        progress = get_candidate_progress(candidate)

        # ── Activity ──
        first_login = candidate.date_joined
        last_login = candidate.last_login or first_login
        days_ago = (now - last_login).days
        is_registered = progress["progress"] == 100
        activity_data = {
            "registration_status": "registered" if is_registered else "in_progress",
            "first_login": first_login,
            "last_login_days_ago": days_ago,
            "activity_7d": days_ago <= 7,
            "activity_30d": days_ago <= 30,
            "activity_90d": days_ago <= 90,
        }

        # ── Profile ──
        resume = Resume.objects.filter(
            candidate=candidate, is_active=True, is_reviewed=True
        ).order_by("-is_main", "-created_at").first()
        profile_data = {
            "completion_percent": progress["progress"],
            "has_resume": resume is not None,
            "career_goal": resume.position if resume else None,
            "email": candidate.email,
            "phone": instance.phone or "",
            "direction": (
                candidate.faculty.domain.name
                if candidate.faculty and candidate.faculty.domain
                else None
            ),
            "faculty": candidate.faculty.name if candidate.faculty else None,
        }

        # ── Applications ──
        applications_qs = list(
            JobApplication.objects
            .filter(candidate=candidate, is_active=True)
            .select_related("vacancy", "vacancy__company", "last_updated_by")
            .order_by("-applied_at")
        )

        # Prefetch all status labels for this candidate's applications.
        company_ids = {a.vacancy.company_id for a in applications_qs}
        if company_ids:
            statuses_qs = ApplicationStatusModel.objects.filter(
                company_id__in=company_ids, is_active=True
            ).values("company_id", "key", "label", "category__key")
            status_labels = {(s["company_id"], s["key"]): s["label"] for s in statuses_qs}
            category_map = {s["key"]: s["category__key"] for s in statuses_qs}
        else:
            status_labels = {}
            category_map = {}

        def _label(app):
            return status_labels.get((app.vacancy.company_id, app.status), app.status)

        applications_data = [
            {
                "id": app.id,
                "title": app.vacancy.title,
                "company": app.vacancy.company.name,
                "applied_at": app.applied_at,
                "status": _label(app),
                "status_key": app.status,
                "source": _("Рекомендация ЦК") if app.last_updated_by_id else _("Самостоятельно"),
            }
            for app in applications_qs
        ]

        # ── Interviews ──
        interview_cats = {StatusCategory.INTERVIEWING, StatusCategory.ASSESSMENT}
        interview_keys = {"INTERVIEW_SCHEDULED", "INTERVIEWED"} | {
            k for k, c in category_map.items() if c in interview_cats
        }
        interview_apps = [a for a in applications_qs if a.status in interview_keys]
        if interview_apps:
            last_interview = interview_apps[0]
            interviews_data = {
                "count": len(interview_apps),
                "last_interview_date": last_interview.applied_at,
                "last_interview_company": last_interview.vacancy.company.name,
                "result": _get_interview_result(last_interview.status),
            }
        else:
            interviews_data = {
                "count": 0,
                "last_interview_date": None,
                "last_interview_company": None,
                "result": None,
            }

        # ── Employment ──
        hired_keys = {"OFFER_ACCEPTED"} | {
            k for k, c in category_map.items() if c == StatusCategory.HIRED
        }
        hired_apps = [
            a for a in applications_qs
            if a.status in hired_keys and a.hired_at
        ]
        if hired_apps:
            current = hired_apps[0]
            employment_data = {
                "is_employed": True,
                "current_company": current.vacancy.company.name,
                "current_position": current.vacancy.title,
                "hire_date": current.hired_at,
                "history": [
                    {
                        "company": app.vacancy.company.name,
                        "position": app.vacancy.title,
                        "start_date": app.hired_at.date() if app.hired_at else None,
                        "end_date": None,
                        "type": app.vacancy.employment_type,
                        "confirmed_by": _("работодатель") if app.last_updated_by_id else _("сотрудник ЦК"),
                    }
                    for app in hired_apps
                ],
            }
        else:
            employment_data = {
                "is_employed": False,
                "current_company": None,
                "current_position": None,
                "hire_date": None,
                "history": [],
            }

        return {
            "activity": activity_data,
            "profile": profile_data,
            "applications": applications_data,
            "interviews": interviews_data,
            "employment": employment_data,
        }


def _get_interview_result(status):
    """Determine interview result from status."""
    if status in ("OFFERED", "OFFER_ACCEPTED"):
        return _("оффер")
    if status in ("REJECTED", "AI_FAILED"):
        return _("отказ")
    return _("нет ответа")
