import logging
import math
import statistics
import time
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from utils.currency_converter import convert_to_uzs

from .hh_client import collect_hh_salaries

logger = logging.getLogger(__name__)

DEFAULT_SALARY_CACHE_TTL = 24 * 60 * 60
LOCK_TIMEOUT = 60

# Below this many disclosed-salary data points, a fresh HH/platform pull is
# considered too noisy to trust on its own (HH listings churn day to day, and
# many vacancies don't disclose salary at all) and gets smoothed against the
# last known-good snapshot instead of replacing it outright.
MIN_TRUSTED_SAMPLE_COUNT = 20
# Floor on how much fresh data is allowed to move the number even when the
# sample is extremely small, so a role never gets permanently stuck.
MIN_BLEND_ALPHA = Decimal("0.15")
# Sample size at/above which we trust raw percentiles over min/max for range.
MIN_SAMPLE_FOR_PERCENTILE_RANGE = 10


def get_salary_cache_ttl():
    from django.conf import settings

    value = getattr(settings, "MARKET_SALARY_CACHE_TTL_SECONDS", DEFAULT_SALARY_CACHE_TTL)
    try:
        return max(int(value), 300)
    except (TypeError, ValueError):
        return DEFAULT_SALARY_CACHE_TTL


def _normalize_role(role):
    return (role or "").strip().lower()


def _compute_median(salaries):
    if not salaries:
        return None
    return Decimal(str(round(statistics.median(salaries), 2))).quantize(Decimal("0.01"))


def _collect_platform_salaries(role):
    from apps.vacancies.models.vacancy import Vacancy

    vacancies = Vacancy.objects.filter(
        title__icontains=role,
        is_active=True,
    ).exclude(
        Q(salary_min__isnull=True) & Q(salary_max__isnull=True),
    ).exclude(
        Q(salary_min=0) & Q(salary_max=0),
    ).only("salary_min", "salary_max", "salary_currency")[:500]
    salaries = []
    for v in vacancies:
        points = []
        if v.salary_min is not None:
            points.append(v.salary_min)
        if v.salary_max is not None:
            points.append(v.salary_max)
        if not points:
            continue
        avg = sum(points) / len(points)
        currency = v.salary_currency or "UZS"
        avg_uzs = convert_to_uzs(avg, currency)
        if avg_uzs is not None:
            salaries.append(round(avg_uzs))
    return salaries


def _collect_hh_salaries(role):
    try:
        raw = collect_hh_salaries(query=role)
    except Exception:
        logger.warning("Failed to collect HH salaries for role=%s", role, exc_info=True)
        return []

    salaries = []
    for item in raw:
        try:
            salary_from = item.get("from")
            salary_to = item.get("to")
            currency = item.get("currency") or "UZS"

            from_val = Decimal(str(salary_from)) if salary_from is not None else None
            to_val = Decimal(str(salary_to)) if salary_to is not None else None

            if from_val is None:
                continue

            if to_val is not None:
                midpoint = (from_val + to_val) / 2
            else:
                midpoint = from_val

            midpoint_uzs = convert_to_uzs(midpoint, currency)
            if midpoint_uzs is not None:
                salaries.append(round(midpoint_uzs))
        except (TypeError, ValueError):
            continue

    return salaries


def _percentile(sorted_values, pct):
    """Linear-interpolation percentile (pct in [0, 1]) over a pre-sorted list."""
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _calc_aggregate(all_salaries):
    if not all_salaries:
        return None
    median = _compute_median(all_salaries)
    sorted_salaries = sorted(all_salaries)

    # A handful of outlier postings (e.g. a single executive-level listing)
    # shouldn't set the displayed range: trim to the 10th/90th percentile
    # once the sample is large enough for percentiles to be meaningful.
    if len(sorted_salaries) >= MIN_SAMPLE_FOR_PERCENTILE_RANGE:
        salary_from = Decimal(str(round(_percentile(sorted_salaries, 0.1))))
        salary_to = Decimal(str(round(_percentile(sorted_salaries, 0.9))))
    else:
        salary_from = Decimal(str(min(sorted_salaries)))
        salary_to = Decimal(str(max(sorted_salaries)))

    return {
        "median_salary_uzs": median,
        "salary_from": salary_from,
        "salary_to": salary_to,
        "sample_count": len(all_salaries),
    }


def _blend_with_previous(new_result, previous):
    """
    Smooth a fresh, thin sample against the last cached snapshot so that
    day-to-day HH listing churn (vacancies added/removed) can't swing the
    displayed number on its own. The less trustworthy the fresh sample, the
    more weight the previous snapshot keeps.
    """
    new_count = new_result["sample_count"]
    alpha = min(Decimal("1"), Decimal(new_count) / Decimal(MIN_TRUSTED_SAMPLE_COUNT))
    alpha = max(alpha, MIN_BLEND_ALPHA)

    def blend(field, prev_value):
        new_value = new_result.get(field)
        if new_value is None:
            return prev_value
        if prev_value is None:
            return new_value
        return (alpha * new_value + (1 - alpha) * prev_value).quantize(Decimal("0.01"))

    return {
        "median_salary_uzs": blend("median_salary_uzs", previous.median_salary_uzs),
        "salary_from": blend("salary_from", previous.salary_from),
        "salary_to": blend("salary_to", previous.salary_to),
        "sample_count": new_count,
        "source": new_result["source"],
    }


def _acquire_lock(cache_key):
    lock_key = f"market_salary_lock:{cache_key}"
    return cache.add(lock_key, "1", timeout=LOCK_TIMEOUT)


def _release_lock(cache_key):
    lock_key = f"market_salary_lock:{cache_key}"
    cache.delete(lock_key)


def _wait_for_cached(cache_key, wait_seconds=3):
    result = None
    for _ in range(int(wait_seconds / 0.5)):
        time.sleep(0.5)
        result = cache.get(cache_key)
        if result is not None:
            break
    return result


def get_market_salary_for_role(role):
    role = _normalize_role(role)
    if not role:
        return None

    cache_key = f"market_salary:{role}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    from apps.general.models import MarketSalaryCache

    db_cache = (
        MarketSalaryCache.objects.filter(role=role)
        .order_by("-created_at")
        .first()
    )
    if db_cache and (timezone.now() - db_cache.created_at).total_seconds() < get_salary_cache_ttl():
        result = {
            "median_salary_uzs": db_cache.median_salary_uzs,
            "salary_from": db_cache.salary_from,
            "salary_to": db_cache.salary_to,
            "sample_count": db_cache.sample_count,
            "source": db_cache.source,
        }
        cache.set(cache_key, result, timeout=get_salary_cache_ttl())
        return result

    got_lock = _acquire_lock(cache_key)
    if not got_lock:
        waited = _wait_for_cached(cache_key)
        if waited is not None:
            return waited
        # ponytail: lock holder slow (HH API > 3s), re-check DB one last time
        # to avoid duplicate expensive HH collection. If still nothing, fallback.
        db_cache = (
            MarketSalaryCache.objects.filter(role=role)
            .order_by("-created_at")
            .first()
        )
        if db_cache and (timezone.now() - db_cache.created_at).total_seconds() < get_salary_cache_ttl():
            result = {
                "median_salary_uzs": db_cache.median_salary_uzs,
                "salary_from": db_cache.salary_from,
                "salary_to": db_cache.salary_to,
                "sample_count": db_cache.sample_count,
                "source": db_cache.source,
            }
            cache.set(cache_key, result, timeout=get_salary_cache_ttl())
            return result
        logger.warning("Cold miss for role=%s after lock wait, insufficient data", role)
        return None

    try:
        previous = db_cache

        platform = _collect_platform_salaries(role)
        hh = _collect_hh_salaries(role)
        all_salaries = platform + hh

        if not all_salaries:
            if previous is not None:
                logger.warning(
                    "Fresh pull for role=%s returned nothing; reusing last snapshot",
                    role,
                )
                result = {
                    "median_salary_uzs": previous.median_salary_uzs,
                    "salary_from": previous.salary_from,
                    "salary_to": previous.salary_to,
                    "sample_count": previous.sample_count,
                    "source": previous.source,
                }
                cache.set(cache_key, result, timeout=get_salary_cache_ttl())
                return result
            logger.warning("No salary data for role=%s", role)
            return None

        result = _calc_aggregate(all_salaries)
        source = "both" if platform and hh else ("platform" if platform else "hh")
        result["source"] = source

        if result["sample_count"] < MIN_TRUSTED_SAMPLE_COUNT and previous is not None:
            result = _blend_with_previous(result, previous)

        ttl = get_salary_cache_ttl()
        cache.set(cache_key, result, timeout=ttl)

        MarketSalaryCache.objects.create(
            role=role,
            source=source,
            median_salary_uzs=result["median_salary_uzs"],
            salary_from=result["salary_from"],
            salary_to=result["salary_to"],
            sample_count=result["sample_count"],
        )

        return result
    finally:
        if got_lock:
            _release_lock(cache_key)
