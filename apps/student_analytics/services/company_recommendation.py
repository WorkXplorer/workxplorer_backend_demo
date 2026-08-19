import random
from collections import defaultdict

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone as django_timezone
from utils.currency_converter import convert_to_uzs

from apps.domain.models import Domain
from apps.matching.services.matching import VacancyMatcher
from apps.profiles.models import CompanyProfile
from apps.subscriptions.models import CompanySubscription
from apps.subscriptions.services import (
    COMPANY_PRO_PLAN_SLUG,
    COMPANY_BASIC_PLAN_SLUG,
    COMPANY_FREE_PLAN_SLUG,
)
from apps.vacancies.models import Vacancy

TIER_PRIORITY = {
    COMPANY_PRO_PLAN_SLUG: 3,
    COMPANY_BASIC_PLAN_SLUG: 2,
    COMPANY_FREE_PLAN_SLUG: 1,
}

MAX_COMPANIES = 7
MATCHING_TOP_K = 100
MIN_SIMILARITY = 0.4


def get_recommended_companies(user):
    today = django_timezone.now().strftime("%Y-%m-%d")
    cache_key = f"recommended_companies_{user.pk}_{today}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from apps.student_analytics.models import StudentAnalytics

    try:
        analytics = StudentAnalytics.objects.select_related("resume").get(candidate=user)
    except StudentAnalytics.DoesNotExist:
        return []

    resume = analytics.resume
    if not resume or resume.embedding is None or not resume.is_embedded:
        return []

    try:
        matching_vacancies = VacancyMatcher.find_matching_vacancies(
            resume, top_k=MATCHING_TOP_K, min_similarity=MIN_SIMILARITY
        )
    except ValueError:
        return []

    if not matching_vacancies:
        return []

    company_vacancies = defaultdict(list)
    for vacancy in matching_vacancies:
        company_vacancies[vacancy.company_id].append(vacancy)

    company_ids = list(company_vacancies.keys())

    profiles = {
        p.company_id: p
        for p in CompanyProfile.objects.filter(company_id__in=company_ids)
    }

    domain_ids = {v.company.domain_id for v in matching_vacancies if v.company.domain_id}
    domains = {d.id: d for d in Domain.objects.filter(id__in=domain_ids)}

    active_subs = {}
    for sub in (
        CompanySubscription.objects.filter(
            company_id__in=company_ids,
            status=CompanySubscription.Status.ACTIVE,
        ).filter(
            Q(expires_at__gte=django_timezone.now()) | Q(expires_at__isnull=True)
        )
        .select_related("plan")
        .order_by("company_id", "-created_at")
    ):
        if sub.company_id not in active_subs:
            active_subs[sub.company_id] = sub

    open_vacancy_counts = {}
    for row in (
        Vacancy.objects.filter(company_id__in=company_ids, is_active=True)
        .values("company_id")
        .annotate(count=Count("id"))
    ):
        open_vacancy_counts[row["company_id"]] = row["count"]

    results = []
    for company_id, vacancies in company_vacancies.items():
        matching_count = len(vacancies)

        salary_mins = [
            s for v in vacancies if v.salary_min is not None
            and (s := convert_to_uzs(v.salary_min, v.salary_currency)) is not None
        ]
        salary_maxs = [
            s for v in vacancies if v.salary_max is not None
            and (s := convert_to_uzs(v.salary_max, v.salary_currency)) is not None
        ]

        salary_min = min(salary_mins) if salary_mins else None
        salary_max = max(salary_maxs) if salary_maxs else None

        sub = active_subs.get(company_id)
        plan_slug = sub.plan.slug if sub else COMPANY_FREE_PLAN_SLUG
        tier = TIER_PRIORITY.get(plan_slug, 0)

        company = vacancies[0].company
        domain = domains.get(company.domain_id) if company.domain_id else None

        profile = profiles.get(company_id)
        employees_count = profile.employees_count if profile else None
        logo = profile.photo.url if profile and profile.photo else None
        has_design = bool(
            profile and (
                profile.photo
                or profile.brand_color_from
                or profile.brand_name_image
            )
        )

        results.append({
            "company_id": company_id,
            "company_name": company.name,
            "logo": logo,
            "domain": domain,
            "employees_count": employees_count,
            "open_vacancies_count": open_vacancy_counts.get(company_id, 0),
            "matching_vacancies_count": matching_count,
            "salary_min": str(salary_min) if salary_min is not None else None,
            "salary_max": str(salary_max) if salary_max is not None else None,
            "is_top_match": matching_count >= 5,
            "subscription_tier": plan_slug,
            "tier_priority": tier,
            "has_design": has_design,
        })

    for r in results:
        r["_rand"] = random.random()
    # Sort: subscription tier first, then companies with design/branding, then random
    results.sort(key=lambda x: (-x["tier_priority"], -x["has_design"], x["_rand"]))
    results = results[:MAX_COMPANIES]

    cache.set(cache_key, results, timeout=86400)
    return results
