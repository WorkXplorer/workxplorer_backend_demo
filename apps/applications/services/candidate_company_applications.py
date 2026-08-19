"""
Shared service for aggregating a candidate's applications within one company.

Powers two API surfaces with a single implementation:
- Company candidates list (per-row summary: total applications + best match)
- Kanban board cards (same summary) and the expandable detail dropdowns
  showing every application of the candidate to the company's vacancies,
  ordered by AI evaluation score (best match first).
"""

from django.utils import timezone

from apps.applications.models import (
    ApplicationStatus,
    ApplicationStatusModel,
    JobApplication,
    StatusCategory,
)
from apps.profiles.models import RecruiterProfile


class CandidateCompanyApplicationsService:
    """
    Aggregates all applications a candidate submitted to a company's vacancies.

    Ordering rule (used everywhere): highest AI evaluation score first,
    applications without a score last, ties broken by newest applied_at.
    The first entry after sorting is the "best match".
    """

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_ai_failed_status_keys(company):
        """Company status keys that mean "auto-rejected by AI evaluation"."""
        return list(
            ApplicationStatusModel.objects.filter(
                company=company,
                category__key=StatusCategory.AI_FAILED,
                is_active=True,
            ).values_list("key", flat=True)
        )

    @classmethod
    def get_candidate_applications(
        cls,
        company,
        candidate_id,
        language="en",
        status_lookup=None,
        recruiter_name_map=None,
        exclude_status_keys=None,
        only_status_keys=None,
    ):
        """
        Full detail payload for one candidate: every application to the
        company's vacancies, best match first.

        Returns None when the candidate has no applications in this company
        (callers translate that into a 404 so cross-company probing is
        indistinguishable from a missing candidate).

        ``status_lookup``/``recruiter_name_map`` let a caller that already
        fetched this company's statuses/recruiter names (e.g. building its
        own serializer context) hand them over instead of paying for the
        same two queries again.

        ``exclude_status_keys``/``only_status_keys`` narrow which applications
        are aggregated so a caller can mirror the visibility rules of the list
        it belongs to (e.g. AI-rejected applications live on their own tab and
        must not leak into the general listing's dropdown).
        """
        applications = cls._fetch_applications(
            company,
            [candidate_id],
            exclude_status_keys=exclude_status_keys,
            only_status_keys=only_status_keys,
        )
        if not applications:
            return None

        entries = cls._build_sorted_entries(
            applications, company, language, status_lookup, recruiter_name_map
        )
        return {
            "candidate_id": str(candidate_id),
            "total_count": len(entries),
            "applications": entries,
        }

    @classmethod
    def get_summary_map(
        cls,
        company,
        candidate_ids,
        language="en",
        status_lookup=None,
        recruiter_name_map=None,
        exclude_status_keys=None,
        only_status_keys=None,
    ):
        """
        Bulk per-candidate summary for list/kanban rows.

        Returns {candidate_id: {"total_count": int, "applications": [entry, ...]}}
        with entries ordered best match first (entries[0].is_best_match=True)
        computed with a constant number of queries regardless of how many
        candidates are on the page.

        ``status_lookup``/``recruiter_name_map`` are optional pre-fetched
        values (see ``get_candidate_applications``) so callers that already
        loaded the company's statuses/recruiter names don't trigger a
        second, redundant round trip for the same data.

        ``exclude_status_keys``/``only_status_keys`` narrow which applications
        are aggregated (see ``get_candidate_applications``).
        """
        candidate_ids = list(candidate_ids)
        if not candidate_ids:
            return {}

        applications = cls._fetch_applications(
            company,
            candidate_ids,
            exclude_status_keys=exclude_status_keys,
            only_status_keys=only_status_keys,
        )
        if not applications:
            return {}

        by_candidate = {}
        for application in applications:
            by_candidate.setdefault(application.candidate_id, []).append(application)

        maps = cls._build_lookup_maps(
            applications, company, language, status_lookup, recruiter_name_map
        )

        summary = {}
        for candidate_id, candidate_apps in by_candidate.items():
            candidate_apps.sort(key=cls._sort_key)
            entries = [
                cls._build_entry(app, maps, is_best_match=(index == 0))
                for index, app in enumerate(candidate_apps)
            ]
            summary[candidate_id] = {
                "total_count": len(entries),
                # Every application this candidate submitted to the company,
                # best match first (entries[0] has is_best_match=True).
                "applications": entries,
                # Deprecated alias kept for existing v1 consumers that read
                # summary["best_match"] directly; new code should use
                # applications[0] instead.
                "best_match": entries[0] if entries else None,
            }
        return summary

    # ------------------------------------------------------------------ #
    # Internals                                                           #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _fetch_applications(
        company, candidate_ids, exclude_status_keys=None, only_status_keys=None
    ):
        """
        One query for all relevant applications.

        Mirrors the visibility rules of the candidates list and kanban:
        demo rows and withdrawn applications are excluded, and only
        vacancies belonging to *this* company are considered. Callers can
        narrow further by status key so the aggregation matches whichever
        list/tab it is rendered under.
        """
        queryset = (
            JobApplication.objects.filter(
                vacancy__company=company,
                candidate_id__in=candidate_ids,
                is_demo=False,
            )
            .exclude(status=ApplicationStatus.WITHDRAWN)
            .select_related("vacancy", "ai_evaluation")
        )
        if only_status_keys:
            queryset = queryset.filter(status__in=list(only_status_keys))
        if exclude_status_keys:
            queryset = queryset.exclude(status__in=list(exclude_status_keys))
        return list(queryset)

    @staticmethod
    def _sort_key(application):
        """Best match first: highest score, scoreless last, newest first on ties."""
        evaluation = getattr(application, "ai_evaluation", None)
        score = getattr(evaluation, "overall_score", None)
        has_no_score = score is None
        applied_ts = application.applied_at.timestamp() if application.applied_at else 0
        return (has_no_score, -(score or 0), -applied_ts)

    @classmethod
    def _build_lookup_maps(
        cls, applications, company, language, status_lookup=None, recruiter_name_map=None
    ):
        """
        Batch-resolve everything entry building needs:
        recruiter names for vacancy creators and localized status labels/colors.

        Accepts optional pre-fetched ``status_lookup`` (iterable of
        ``ApplicationStatusModel``) and ``recruiter_name_map``
        (``{recruiter_id: full_name}``) so a
        caller that already loaded this data for its own purposes doesn't
        cause it to be fetched again. Only recruiter ids missing from a
        supplied map are queried, since the caller's set may be scoped
        narrower (e.g. one page) than what this method needs.
        """
        recruiter_ids = {
            app.vacancy.created_by_id
            for app in applications
            if app.vacancy.created_by_id
        }
        recruiter_name_map = dict(recruiter_name_map) if recruiter_name_map else {}
        missing_recruiter_ids = recruiter_ids - recruiter_name_map.keys()
        if missing_recruiter_ids:
            profiles = RecruiterProfile.objects.filter(
                recruiter_id__in=missing_recruiter_ids
            ).values("recruiter_id", "full_name")
            for p in profiles:
                recruiter_name_map[p["recruiter_id"]] = p["full_name"]

        if status_lookup is None:
            status_lookup = ApplicationStatusModel.objects.filter(
                company=company,
                is_active=True,
            )

        status_label_map = {}
        status_color_map = {}
        for status in status_lookup:
            status_label_map[status.key] = status.get_localized_label(language)
            status_color_map[status.key] = status.color

        return {
            "recruiter_names": recruiter_name_map,
            "status_labels": status_label_map,
            "status_colors": status_color_map,
            "language": language,
        }

    @classmethod
    def _build_sorted_entries(
        cls, applications, company, language, status_lookup=None, recruiter_name_map=None
    ):
        maps = cls._build_lookup_maps(
            applications, company, language, status_lookup, recruiter_name_map
        )
        applications = sorted(applications, key=cls._sort_key)
        return [
            cls._build_entry(app, maps, is_best_match=(index == 0))
            for index, app in enumerate(applications)
        ]

    @classmethod
    def _build_entry(cls, application, maps, is_best_match=False):
        vacancy = application.vacancy
        evaluation = getattr(application, "ai_evaluation", None)
        score = getattr(evaluation, "overall_score", None)

        ai_passed = None
        if score is not None:
            ai_passed = score >= (vacancy.minimum_ai_score or 0)

        applied_at = application.applied_at
        applied_at_display = (
            timezone.localtime(applied_at).strftime("%d.%m.%Y") if applied_at else None
        )

        recruiter_id = vacancy.created_by_id
        recruiter = None
        if recruiter_id:
            recruiter = {
                "id": str(recruiter_id),
                "full_name": maps["recruiter_names"].get(recruiter_id),
            }

        return {
            "application_id": str(application.id),
            "vacancy_id": str(application.vacancy_id),
            "vacancy_title": vacancy.title,
            "applied_at": applied_at_display,
            "ai_score": score,
            "ai_evaluation_status": getattr(evaluation, "status", "pending"),
            "ai_passed": ai_passed,
            "status": application.status,
            "status_label": cls._resolve_status_label(application.status, maps),
            "status_color": maps["status_colors"].get(application.status),
            "is_best_match": is_best_match,
            "recruiter": recruiter,
            # Salary the company set on the vacancy ("-" when unspecified).
            "salary": cls._format_vacancy_salary(vacancy),
        }

    @classmethod
    def _format_vacancy_salary(cls, vacancy):
        """
        Human-readable salary the company posted for the vacancy.

        Returns ``"-"`` when neither bound is set so the frontend can render
        it directly.
        """
        salary_min = vacancy.salary_min
        salary_max = vacancy.salary_max
        currency = vacancy.salary_currency or ""

        if salary_min and salary_max:
            return (
                f"{cls._format_amount(salary_min)} - "
                f"{cls._format_amount(salary_max)} {currency}"
            ).strip()
        if salary_min:
            return f"{cls._format_amount(salary_min)} {currency}".strip()
        if salary_max:
            return f"{cls._format_amount(salary_max)} {currency}".strip()
        return "-"

    @staticmethod
    def _format_amount(amount):
        """
        Thousands-grouped amount, preserving cents when present.

        ``:,.0f`` alone would truncate fractional values (e.g. an hourly
        rate of 45.50 becomes "46"), so whole numbers are shown without a
        decimal part and fractional ones keep two decimal places.
        """
        if amount == amount.to_integral_value():
            return f"{amount:,.0f}"
        return f"{amount:,.2f}"

    @staticmethod
    def _resolve_status_label(status_key, maps):
        """Company-specific label first, legacy enum translation as fallback."""
        label = maps["status_labels"].get(status_key)
        if label:
            return label

        try:
            status_choice = ApplicationStatus(status_key)
        except ValueError:
            return str(status_key).replace("_", " ").title()

        translations = ApplicationStatus.get_translations().get(status_choice, {})
        return translations.get(
            maps["language"],
            translations.get("en", status_choice.label),
        )
    # ------------------------------------------------------------------ #
