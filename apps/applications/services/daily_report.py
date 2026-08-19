"""
Daily job-application report for the Telegram group.

Builds a snapshot of platform activity — applications and their funnel, the
companies receiving them, and the universities sending them — and ships it to
the WorkXplorer Telegram bot, which renders it into the three messages posted
to the reporting topic. Everything here produces numbers only; the bot owns
every word of the wording and layout.

All date windows are computed in the project's local timezone
(``settings.TIME_ZONE``, Asia/Tashkent) so "yesterday" means a full local day,
not a UTC one.
"""

import logging
from datetime import date, datetime, time, timedelta

import requests
from django.conf import settings
from django.db.models import Avg, Count, Exists, F, Min, OuterRef, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# How many companies are listed by name before the rest are folded into a
# single "and N more" line. Keeps the message readable on mobile.
DEFAULT_TOP_COMPANIES = 5

# Same idea for the per-university signup list.
DEFAULT_TOP_UNIVERSITIES = 5

# Same idea for the per-vacancy list in the applications report.
DEFAULT_TOP_VACANCIES = 3

# Same idea for the recently-active recruiter list.
DEFAULT_TOP_RECRUITERS = 5

# A vacancy is called idle once it has gone this long without an application.
# Long enough that a quiet weekend doesn't flag half the board.
IDLE_VACANCY_DAYS = 7

# How long a user has to stay away before they count as churned. A month is
# long enough that a student on exam break or a recruiter between hiring
# rounds isn't written off.
CHURN_WINDOW_DAYS = 30


def _local_midnight(day: date) -> datetime:
    """Return an aware datetime for 00:00 of ``day`` in the local timezone."""
    return timezone.make_aware(
        datetime.combine(day, time.min), timezone.get_current_timezone()
    )


def _window(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    """Half-open ``[start_day 00:00, end_day 00:00)`` window as aware datetimes."""
    return _local_midnight(start_day), _local_midnight(end_day)


# Legacy ``ApplicationStatus`` values predate the per-company status system and
# are still present on older rows, so they are mapped onto the same analytics
# categories rather than shown as a separate vocabulary.
LEGACY_STATUS_CATEGORIES = {
    "APPLIED": "APPLIED",
    "INTERVIEW_SCHEDULED": "INTERVIEWING",
    "INTERVIEWED": "INTERVIEWING",
    "OFFERED": "OFFERED",
    "OFFER_ACCEPTED": "HIRED",
    "OFFER_REJECTED": "OFFER_REJECTED",
    "WITHDRAWN": "WITHDRAWN",
    "REJECTED": "REJECTED",
    "AI_FAILED": "AI_FAILED",
}

# Bucket for status keys that map to neither a company status nor a legacy one.
OTHER_CATEGORY = "OTHER"


def _status_breakdown(day_filter: Q) -> dict:
    """
    Group applications by analytics status category, for the day and all time.

    ``JobApplication.status`` holds a company-scoped status *key*, not a
    foreign key, so the mapping to a :class:`StatusCategory` lives in
    ``ApplicationStatusModel`` and cannot be joined in the ORM. The status
    table is small (a handful of rows per company), so it is loaded once and
    the grouped counts are folded onto it in Python.

    Returns ``{"day": {category: count}, "all_time": {category: count}}`` with
    zero-count categories omitted.
    """
    from apps.applications.models import ApplicationStatusModel, JobApplication

    category_by_company_key = {
        (company_id, key): category_key
        for company_id, key, category_key in ApplicationStatusModel.objects.values_list(
            "company_id", "key", "category__key"
        )
    }

    rows = JobApplication.objects.values("vacancy__company_id", "status").annotate(
        day_count=Count("id", filter=day_filter),
        all_time_count=Count("id"),
    )

    day_counts: dict[str, int] = {}
    all_time_counts: dict[str, int] = {}

    for row in rows:
        status_key = row["status"]
        category = category_by_company_key.get(
            (row["vacancy__company_id"], status_key)
        ) or LEGACY_STATUS_CATEGORIES.get(status_key, OTHER_CATEGORY)

        if row["day_count"]:
            day_counts[category] = day_counts.get(category, 0) + row["day_count"]
        if row["all_time_count"]:
            all_time_counts[category] = (
                all_time_counts.get(category, 0) + row["all_time_count"]
            )

    return {"day": day_counts, "all_time": all_time_counts}


def _vacancy_breakdown(day_filter: Q, week_filter: Q, top_vacancies: int) -> dict:
    """
    Rank the vacancies that received applications on the report date.

    The company breakdown says *who* is hiring; this says *what* for, which is
    what tells a quiet day (one vacancy going viral) apart from a broad one.
    """
    from apps.applications.models import JobApplication

    rows = list(
        JobApplication.objects.values(
            "vacancy_id", "vacancy__title", "vacancy__company__name"
        )
        .annotate(
            day_count=Count("id", filter=day_filter),
            week_count=Count("id", filter=week_filter),
            all_time_count=Count("id"),
        )
        .filter(day_count__gt=0)
        .order_by("-day_count", "-week_count", "-all_time_count")
    )

    listed = rows[:top_vacancies]
    remainder = rows[top_vacancies:]

    return {
        "vacancies": [
            {
                "title": row["vacancy__title"] or "—",
                "company": row["vacancy__company__name"] or "—",
                "day": row["day_count"],
                "week": row["week_count"],
                "all_time": row["all_time_count"],
            }
            for row in listed
        ],
        "vacancies_active": len(rows),
        "vacancies_hidden": len(remainder),
        "vacancies_hidden_day": sum(row["day_count"] for row in remainder),
    }


def _funnel() -> dict:
    """
    All-time progression: viewed → applied → reached review → hired.

    The three application stages are deliberately built from the
    ``in_review_at`` / ``hired_at`` timestamps rather than the current status.
    An application that was interviewed and then rejected has left the
    interviewing bucket, so counting current statuses would understate how far
    the pipeline actually gets.
    """
    from apps.applications.models import JobApplication
    from apps.vacancies.models import VacancyView

    stages = JobApplication.objects.aggregate(
        applied=Count("id"),
        reviewed=Count("id", filter=Q(in_review_at__isnull=False)),
        hired=Count("id", filter=Q(hired_at__isnull=False)),
        time_to_hire=Avg(
            F("hired_at") - F("applied_at"), filter=Q(hired_at__isnull=False)
        ),
    )

    time_to_hire = stages.pop("time_to_hire")
    return {
        **stages,
        "views": VacancyView.objects.count(),
        # Days rather than a duration: the bot only ever prints it rounded, and
        # a timedelta doesn't survive the JSON round-trip to it. Checked against
        # None, not truthiness — a candidate hired the same day they applied
        # averages to zero, which is a number, not missing data.
        "days_to_hire": (
            round(time_to_hire.total_seconds() / 86400, 1)
            if time_to_hire is not None
            else None
        ),
    }


def _ai_breakdown(day_start: datetime, day_end: datetime) -> dict:
    """
    AI screening quality for the report date, plus an all-time baseline.

    Only completed evaluations carry a score, so pending and failed ones are
    excluded from the average instead of being counted as zero. The day window
    follows the application's ``applied_at``, not the evaluation's own
    timestamp, so the average lines up with the applications reported above it.
    """
    from apps.applications.models import ApplicationAIEvaluation, EvaluationStatus

    day_scope = Q(
        application__applied_at__gte=day_start, application__applied_at__lt=day_end
    )
    completed = Q(status=EvaluationStatus.COMPLETED, overall_score__isnull=False)

    stats = ApplicationAIEvaluation.objects.aggregate(
        evaluated=Count("id", filter=day_scope & completed),
        avg_score=Avg("overall_score", filter=day_scope & completed),
        avg_score_all_time=Avg("overall_score", filter=completed),
    )

    # Averages are checked against None rather than truthiness: a day where the
    # AI scored everything zero is a finding, not an absence of one.
    return {
        "evaluated": stats["evaluated"] or 0,
        "avg_score": (
            round(stats["avg_score"], 1) if stats["avg_score"] is not None else None
        ),
        "avg_score_all_time": (
            round(stats["avg_score_all_time"], 1)
            if stats["avg_score_all_time"] is not None
            else None
        ),
    }


def _applicant_breakdown(day_start: datetime, day_end: datetime) -> dict:
    """
    How many people are behind the day's applications, and how many are new.

    Applications alone can't tell twenty candidates applying once from one
    candidate applying twenty times, and "first time" separates genuinely new
    demand from the regulars working through the board.
    """
    from apps.applications.models import JobApplication

    day_scope = JobApplication.objects.filter(
        applied_at__gte=day_start, applied_at__lt=day_end
    )

    first_time = (
        JobApplication.objects.values("candidate_id")
        .annotate(first_applied=Min("applied_at"))
        .filter(first_applied__gte=day_start, first_applied__lt=day_end)
        .count()
    )

    return {
        "candidates": day_scope.values("candidate_id").distinct().count(),
        "first_time": first_time,
    }


def _marketplace(day_start: datetime, day_end: datetime) -> dict:
    """
    Supply side of the platform: what's open, what's new, what nobody wants.

    ``idle`` counts open vacancies that have gone :data:`IDLE_VACANCY_DAYS`
    without applications; vacancies younger than that window are excluded,
    because a job posted yesterday is not stale, it's new.

    ``saved_not_applied`` is demand that stopped one click short — a candidate
    bookmarked the vacancy and never applied — which is the cheapest list of
    people to go after.
    """
    from apps.applications.models import JobApplication
    from apps.authentication.models import Company
    from apps.vacancies.models import FavouriteVacancy, Vacancy, VacancyView

    idle_cutoff = day_end - timedelta(days=IDLE_VACANCY_DAYS)
    open_vacancies = Vacancy.objects.filter(is_active=True).count()
    views_day = VacancyView.objects.filter(
        viewed_at__gte=day_start, viewed_at__lt=day_end
    ).count()

    applied_by_same_candidate = JobApplication.objects.filter(
        vacancy=OuterRef("vacancy_id"), candidate=OuterRef("candidate_id")
    )

    return {
        "open_vacancies": open_vacancies,
        "new_vacancies": Vacancy.objects.filter(
            created_at__gte=day_start, created_at__lt=day_end
        ).count(),
        "new_companies": Company.objects.filter(
            created_at__gte=day_start, created_at__lt=day_end
        ).count(),
        "views_day": views_day,
        "views_per_vacancy": (
            round(views_day / open_vacancies, 1) if open_vacancies else None
        ),
        "idle_vacancies": (
            Vacancy.objects.filter(is_active=True, created_at__lt=idle_cutoff)
            .exclude(applications__applied_at__gte=idle_cutoff)
            .count()
        ),
        "idle_after_days": IDLE_VACANCY_DAYS,
        "saved_not_applied": (
            FavouriteVacancy.objects.annotate(
                has_application=Exists(applied_by_same_candidate)
            )
            .filter(has_application=False)
            .count()
        ),
    }


def _roadmap_breakdown(
    day_start: datetime, day_end: datetime, week_start: datetime, week_end: datetime
) -> dict:
    """
    Career-roadmap activity: who is planning a career, not just chasing a job.

    A roadmap is generated per student, so the count of roadmaps is the count
    of students who asked for one.
    """
    from apps.student_analytics.models import SkillRoadmap

    roadmaps = SkillRoadmap.objects.aggregate(
        day=Count(
            "id", filter=Q(generated_at__gte=day_start, generated_at__lt=day_end)
        ),
        week=Count(
            "id", filter=Q(generated_at__gte=week_start, generated_at__lt=week_end)
        ),
        all_time=Count("id"),
    )

    return roadmaps


def _signup_breakdown(
    day_start: datetime,
    day_end: datetime,
    prev_day_start: datetime,
    prev_day_end: datetime,
    week_start: datetime,
    week_end: datetime,
    prev_week_start: datetime,
    prev_week_end: datetime,
    top_universities: int,
) -> dict:
    """
    Count new candidate signups, overall and per university.

    Candidates sign up with or without an educational partner, so the
    unaffiliated ones are reported as their own bucket rather than being
    dropped or ranked alongside named universities — otherwise the per-university
    numbers wouldn't reconcile with the totals.
    """
    from apps.authentication.models import Candidate

    day_filter = Q(date_joined__gte=day_start, date_joined__lt=day_end)
    week_filter = Q(date_joined__gte=week_start, date_joined__lt=week_end)

    totals = Candidate.objects.aggregate(
        day=Count("id", filter=day_filter),
        prev_day=Count(
            "id", filter=Q(date_joined__gte=prev_day_start, date_joined__lt=prev_day_end)
        ),
        week=Count("id", filter=week_filter),
        prev_week=Count(
            "id",
            filter=Q(date_joined__gte=prev_week_start, date_joined__lt=prev_week_end),
        ),
        all_time=Count("id"),
    )

    rows = list(
        Candidate.objects.values("edupartner_id", "edupartner__name").annotate(
            day_count=Count("id", filter=day_filter),
            week_count=Count("id", filter=week_filter),
            all_time_count=Count("id"),
        )
    )

    no_university = {"day": 0, "week": 0, "all_time": 0}
    named = []
    for row in rows:
        if row["edupartner_id"] is None:
            no_university = {
                "day": row["day_count"],
                "week": row["week_count"],
                "all_time": row["all_time_count"],
            }
            continue
        named.append(
            {
                "name": row["edupartner__name"] or "—",
                "day": row["day_count"],
                "week": row["week_count"],
                "all_time": row["all_time_count"],
            }
        )

    named.sort(key=lambda r: (-r["day"], -r["week"], -r["all_time"]))
    active = [row for row in named if row["day"] > 0]
    listed = active[:top_universities]
    remainder = active[top_universities:]

    return {
        "totals": totals,
        "universities": listed,
        "universities_active": len(active),
        "universities_total": len(named),
        "universities_hidden": len(remainder),
        "universities_hidden_day": sum(row["day"] for row in remainder),
        "no_university": no_university,
    }


def _education_breakdown(
    day_filter: Q,
    week_filter: Q,
    day_start: datetime,
    day_end: datetime,
    top_universities: int,
) -> dict:
    """
    Everything the university report is built from.

    Signups say how many students *joined* from each university; this says how
    many of them actually apply, which is the number an education partner is
    judged on — a university that sends hundreds of registrations and no
    applications looks identical to a good one in the signup list alone.
    """
    from apps.applications.models import JobApplication
    from apps.authentication.models import Candidate
    from apps.skill_tests.models import TestAttempt

    rows = list(
        JobApplication.objects.values(
            "candidate__edupartner_id", "candidate__edupartner__name"
        ).annotate(
            day_count=Count("id", filter=day_filter),
            week_count=Count("id", filter=week_filter),
            all_time_count=Count("id"),
        )
    )

    no_university = {"day": 0, "week": 0, "all_time": 0}
    named = []
    for row in rows:
        entry = {
            "day": row["day_count"],
            "week": row["week_count"],
            "all_time": row["all_time_count"],
        }
        if row["candidate__edupartner_id"] is None:
            # A candidate with no university is one row in this grouping, so
            # the bucket is assigned rather than accumulated.
            no_university = entry
            continue
        named.append(
            {
                "id": str(row["candidate__edupartner_id"]),
                "name": row["candidate__edupartner__name"] or "—",
                **entry,
            }
        )

    named.sort(key=lambda r: (-r["day"], -r["week"], -r["all_time"]))
    active = [row for row in named if row["day"] > 0]
    listed = active[:top_universities]
    remainder = active[top_universities:]

    # Whether the day's new users arrive with a resume: a signup that never
    # builds one cannot apply, so this is the first place a bad funnel shows.
    new_users = Candidate.objects.filter(
        date_joined__gte=day_start, date_joined__lt=day_end
    ).aggregate(
        total=Count("id", distinct=True),
        with_resume=Count("id", filter=Q(resumes__isnull=False), distinct=True),
    )

    day_attempts = TestAttempt.objects.filter(
        created_at__gte=day_start, created_at__lt=day_end
    )

    return {
        "universities": listed,
        "universities_active": len(active),
        "universities_total": len(named),
        "universities_hidden": len(remainder),
        "universities_hidden_day": sum(row["day"] for row in remainder),
        "no_university": no_university,
        "resumes": {
            "new_users": new_users["total"] or 0,
            "with_resume": new_users["with_resume"] or 0,
        },
        "tests": {
            "attempts": day_attempts.count(),
            "students": day_attempts.values("candidate_id").distinct().count(),
        },
        # Registered but never applied. A university sending signups that never
        # turn into applications looks fine in the signup list and is the whole
        # problem, so the two numbers belong in the same report.
        "never_applied": Candidate.objects.filter(applications__isnull=True).count(),
    }


def _candidate_base() -> dict:
    """
    How far the whole candidate base has actually got, all time.

    The report already counts how many of *the day's* signups arrive with a
    resume, which says nothing about the several hundred who registered months
    ago and stopped. These are the standing totals: everyone who ever
    registered, and how many of them completed each step after it.

    A profile and a resume are separate things and both are optional — a
    profile is created through its own endpoint, a resume through another — so
    a candidate can hold either, both or neither. They are counted separately
    rather than collapsed into one "complete" figure, because which step people
    stop at is the useful part.

    ``distinct=True`` throughout is load-bearing: ``resumes`` is a reverse
    foreign key, so a candidate with three resumes joins to three rows and
    would otherwise inflate every count in this aggregate, not just its own.
    """
    from apps.authentication.models import Candidate

    counts = Candidate.objects.aggregate(
        all_time=Count("id", distinct=True),
        with_profile=Count(
            "id", filter=Q(candidateprofile__isnull=False), distinct=True
        ),
        with_resume=Count("id", filter=Q(resumes__isnull=False), distinct=True),
        ever_applied=Count(
            "id", filter=Q(applications__isnull=False), distinct=True
        ),
    )
    return {key: value or 0 for key, value in counts.items()}


def _mobile_users_breakdown(
    day_start: datetime, day_end: datetime, week_start: datetime, week_end: datetime
) -> dict:
    """
    Unique users who used the native mobile app, by activity window.

    "Used" means an active ``MobileSession`` was touched (``last_used_at``),
    not merely installed — an install that never logs back in shouldn't count
    as a day-1 mobile user forever. ``distinct=True`` matters here for the
    same reason as ``_candidate_base``: one user can hold both an iOS and an
    Android session, or several devices on the same platform, and would
    otherwise be counted once per session instead of once per user.
    """
    from apps.authentication.models import MobileSession

    sessions = MobileSession.objects.filter(status=MobileSession.Status.ACTIVE)

    counts = sessions.aggregate(
        day=Count(
            "user_id",
            filter=Q(last_used_at__gte=day_start, last_used_at__lt=day_end),
            distinct=True,
        ),
        week=Count(
            "user_id",
            filter=Q(last_used_at__gte=week_start, last_used_at__lt=week_end),
            distinct=True,
        ),
        all_time=Count("user_id", distinct=True),
    )

    platform_rows = sessions.filter(
        last_used_at__gte=day_start, last_used_at__lt=day_end
    ).values("platform").annotate(users=Count("user_id", distinct=True))
    by_platform = {row["platform"]: row["users"] for row in platform_rows}

    return {
        "day": counts["day"] or 0,
        "week": counts["week"] or 0,
        "all_time": counts["all_time"] or 0,
        "ios_day": by_platform.get(MobileSession.Platform.IOS, 0),
        "android_day": by_platform.get(MobileSession.Platform.ANDROID, 0),
    }


def _churn_for(manager, cutoff: datetime) -> dict:
    """
    Split one audience into active, churned, and never-signed-in.

    The denominator is deliberately the users who have logged in at least once,
    not every registered account: someone who registered and never came back
    hasn't churned, they never arrived, and folding the two together makes a
    signup problem read as a retention one. They are reported alongside as
    ``never_logged_in`` so the two numbers can still be added up.
    """
    known = manager.filter(is_active=True, last_login__isnull=False)
    total = known.count()
    churned = known.filter(last_login__lt=cutoff).count()

    return {
        "known": total,
        "active": total - churned,
        "churned": churned,
        # Checked against the count, not truthiness: a zero churn rate is a
        # result, an empty audience is not.
        "rate": round(churned / total * 100, 1) if total else None,
        "never_logged_in": manager.filter(
            is_active=True, last_login__isnull=True
        ).count(),
    }


def _churn_breakdown(day_end: datetime, window_days: int) -> dict:
    """
    Churn for both sides of the marketplace, as of the report date.

    Churn here is dormancy: the share of users who have signed in at some point
    but not within the last ``window_days``. It is not a cohort measure —
    ``last_login`` keeps only the most recent sign-in, with no history behind
    it, so there is no way to ask who was active last month and failed to
    return this one. That also means the number cannot be trended against an
    earlier day, and none is reported: a rerun for an old date sees today's
    ``last_login`` values, so it answers "who is dormant now", not "who was
    dormant then".

    Candidates and recruiters are kept apart because they churn for unrelated
    reasons — a student who found a job and a recruiter who stopped hiring are
    the same number and opposite news.
    """
    from apps.authentication.models import Candidate, Recruiter

    cutoff = day_end - timedelta(days=window_days)

    return {
        "window_days": window_days,
        "candidates": _churn_for(Candidate.objects, cutoff),
        "recruiters": _churn_for(Recruiter.objects, cutoff),
    }


def _recruiter_logins(day_end: datetime, top_recruiters: int) -> dict:
    """
    The recruiters who signed in most recently, and how many are dormant.

    The churn block says what share of recruiters have gone quiet; this names
    the ones still showing up, which is the list someone actually acts on —
    a company whose only recruiter last signed in six weeks ago is a call to
    make, not a percentage.
    """
    from apps.authentication.models import Recruiter
    from apps.profiles.models import RecruiterProfile

    rows = list(
        Recruiter.objects.filter(is_active=True, last_login__isnull=False)
        .values("id", "last_login", "company__name")
        .order_by("-last_login")[:top_recruiters]
    )

    # A recruiter can have more than one profile row, so the names are fetched
    # separately rather than joined — a join would multiply the ranked rows and
    # push real recruiters out of the top five.
    names = {}
    for recruiter_id, full_name in RecruiterProfile.objects.filter(
        recruiter_id__in=[row["id"] for row in rows]
    ).values_list("recruiter_id", "full_name"):
        if full_name and recruiter_id not in names:
            names[recruiter_id] = full_name

    return {
        "recent": [
            {
                "name": names.get(row["id"]) or "—",
                "company": row["company__name"] or "—",
                "last_login": row["last_login"].isoformat(),
                # Clamped at zero: a report rerun for an older date sees logins
                # that happened after its window, and "-3 days ago" is noise.
                "days_ago": max(0, (day_end - row["last_login"]).days),
            }
            for row in rows
        ],
        "total": Recruiter.objects.filter(is_active=True).count(),
    }


def build_daily_application_report(
    report_date: date | None = None,
    top_companies: int | None = None,
) -> dict:
    """
    Collect application statistics for the daily Telegram report.

    Args:
        report_date: The day the report is about. Defaults to yesterday
            (local time), since the report runs in the morning about the
            previous, completed day.
        top_companies: How many companies to list by name.

    Returns:
        A JSON-serialisable payload consumed by the bot's
        ``/api/reports/daily-applications`` endpoint. The bot owns all
        formatting — this function only produces numbers.
    """
    from apps.applications.models import JobApplication

    if top_companies is None:
        top_companies = getattr(
            settings, "DAILY_APPLICATION_REPORT_TOP_COMPANIES", DEFAULT_TOP_COMPANIES
        )

    today = timezone.localdate()
    if report_date is None:
        report_date = today - timedelta(days=1)

    # Day windows: the report date itself, and the day before it for a trend.
    day_start, day_end = _window(report_date, report_date + timedelta(days=1))
    prev_day_start, prev_day_end = _window(report_date - timedelta(days=1), report_date)

    # Week windows: the ISO week (Mon-Sun) that the report date belongs to,
    # up to and including the report date, and the same-length window one week
    # earlier. Anchoring on the report date (not today) means a Monday run
    # reports on the week that just finished instead of an empty one.
    week_start_day = report_date - timedelta(days=report_date.weekday())
    week_start, week_end = _window(week_start_day, report_date + timedelta(days=1))
    prev_week_start, prev_week_end = _window(
        week_start_day - timedelta(days=7), report_date - timedelta(days=6)
    )

    day_filter = Q(applied_at__gte=day_start, applied_at__lt=day_end)
    week_filter = Q(applied_at__gte=week_start, applied_at__lt=week_end)

    # One grouped aggregate covers every per-company number we need.
    company_rows = (
        JobApplication.objects.values("vacancy__company_id", "vacancy__company__name")
        .annotate(
            day_count=Count("id", filter=day_filter),
            week_count=Count("id", filter=week_filter),
            all_time_count=Count("id"),
        )
        .order_by("-day_count", "-week_count", "-all_time_count")
    )
    company_rows = list(company_rows)

    active_rows = [row for row in company_rows if row["day_count"] > 0]
    listed = active_rows[:top_companies]
    remainder = active_rows[top_companies:]

    totals = JobApplication.objects.aggregate(
        all_time=Count("id"),
        day=Count("id", filter=day_filter),
        prev_day=Count(
            "id", filter=Q(applied_at__gte=prev_day_start, applied_at__lt=prev_day_end)
        ),
        week=Count("id", filter=week_filter),
        prev_week=Count(
            "id",
            filter=Q(applied_at__gte=prev_week_start, applied_at__lt=prev_week_end),
        ),
    )

    statuses = _status_breakdown(day_filter)

    signups = _signup_breakdown(
        day_start,
        day_end,
        prev_day_start,
        prev_day_end,
        week_start,
        week_end,
        prev_week_start,
        prev_week_end,
        getattr(
            settings,
            "DAILY_APPLICATION_REPORT_TOP_UNIVERSITIES",
            DEFAULT_TOP_UNIVERSITIES,
        ),
    )

    education = _education_breakdown(
        day_filter,
        week_filter,
        day_start,
        day_end,
        getattr(
            settings,
            "DAILY_APPLICATION_REPORT_TOP_UNIVERSITIES",
            DEFAULT_TOP_UNIVERSITIES,
        ),
    )

    vacancies = _vacancy_breakdown(
        day_filter,
        week_filter,
        getattr(
            settings, "DAILY_APPLICATION_REPORT_TOP_VACANCIES", DEFAULT_TOP_VACANCIES
        ),
    )

    ai = _ai_breakdown(day_start, day_end)
    # The rejection count comes from the status breakdown rather than a second
    # query: an auto-rejected application is exactly one sitting in AI_FAILED.
    ai["rejected"] = statuses["day"].get("AI_FAILED", 0)

    # Days of the week the report date covers, so the bot can put the day's
    # count next to the week's running average instead of only yesterday —
    # a single day swings wildly, the average doesn't.
    week_days = (report_date - week_start_day).days + 1

    return {
        "report_date": report_date.isoformat(),
        "week_start": week_start_day.isoformat(),
        "timezone": str(timezone.get_current_timezone()),
        "totals": {
            "all_time": totals["all_time"],
            "day": totals["day"],
            "prev_day": totals["prev_day"],
            "week": totals["week"],
            "prev_week": totals["prev_week"],
            "week_days": week_days,
            "week_avg_day": round(totals["week"] / week_days, 1),
        },
        "statuses": statuses,
        "signups": signups,
        "education": education,
        "candidates": _candidate_base(),
        "mobile": _mobile_users_breakdown(day_start, day_end, week_start, week_end),
        "roadmaps": _roadmap_breakdown(day_start, day_end, week_start, week_end),
        "funnel": _funnel(),
        "ai": ai,
        "applicants": _applicant_breakdown(day_start, day_end),
        "marketplace": _marketplace(day_start, day_end),
        "churn": _churn_breakdown(
            day_end,
            getattr(settings, "DAILY_APPLICATION_REPORT_CHURN_DAYS", CHURN_WINDOW_DAYS),
        ),
        "recruiters": _recruiter_logins(
            day_end,
            getattr(
                settings, "DAILY_APPLICATION_REPORT_TOP_RECRUITERS", DEFAULT_TOP_RECRUITERS
            ),
        ),
        **vacancies,
        "companies": [
            {
                "name": row["vacancy__company__name"] or "—",
                "day": row["day_count"],
                "week": row["week_count"],
                "all_time": row["all_time_count"],
            }
            for row in listed
        ],
        "companies_active": len(active_rows),
        "companies_total": len(company_rows),
        "companies_hidden": len(remainder),
        "companies_hidden_day": sum(row["day_count"] for row in remainder),
    }


def send_daily_application_report(payload: dict) -> bool:
    """
    POST the report payload to the Telegram bot API.

    Returns True when the bot accepted the report. Network problems are
    retried a few times; anything else is logged and reported as a failure so
    the caller can surface it.
    """
    api_secret = getattr(settings, "TELEGRAM_BOT_API_SECRET", "")
    if not api_secret:
        logger.warning(
            "TELEGRAM_BOT_API_SECRET not configured — skipping daily application report"
        )
        return False

    url = f"{settings.TELEGRAM_BOT_API_URL.rstrip('/')}/api/reports/daily-applications"
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"X-API-Secret": api_secret},
                timeout=15,
            )
            if response.status_code == 200:
                logger.info(
                    "Daily application report for %s sent to Telegram",
                    payload.get("report_date"),
                )
                return True
            logger.warning(
                "Daily application report attempt %d/%d failed: HTTP %s — %s",
                attempt,
                max_retries,
                response.status_code,
                response.text[:200],
            )
        except requests.RequestException as exc:
            logger.warning(
                "Daily application report attempt %d/%d failed: %s",
                attempt,
                max_retries,
                exc,
            )

        if attempt < max_retries:
            import time as _time

            _time.sleep(2**attempt)

    logger.error(
        "Daily application report for %s failed after %d attempts",
        payload.get("report_date"),
        max_retries,
    )
    return False
