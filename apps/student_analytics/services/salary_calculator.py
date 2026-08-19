import logging
from decimal import Decimal

from django.utils import timezone

from apps.general.services.market_salary_cache import get_market_salary_for_role
from apps.resumes.services.experience import calculate_total_experience_months

logger = logging.getLogger(__name__)

# Experience -> percentile position within the market distribution. Unlike a
# flat coefficient (old model), this has no ceiling: a 30-year veteran keeps
# climbing toward the top of the distribution instead of being capped at the
# same multiplier as a 5-year hire.
EXPERIENCE_PERCENTILES = [
    (0, Decimal("0.10")),
    (12, Decimal("0.25")),
    (36, Decimal("0.50")),
    (60, Decimal("0.65")),
    (96, Decimal("0.80")),
    (144, Decimal("0.90")),
    (216, Decimal("0.97")),
]
POTENTIAL_PERCENTILE_UPLIFT = Decimal("0.15")
MAX_PERCENTILE = Decimal("0.97")

_P10 = Decimal("0.10")
_P50 = Decimal("0.50")
_P90 = Decimal("0.90")

# How much weight the role-level HH/platform sample gets against the stat.uz
# sector nominal salary, scaled by sample size. Capped below 1.0 so the
# official sector figure always has *some* pull, even on a well-sampled
# role query -- it's the one source immune to "the query text happened to
# match different vacancies this week."
SECTOR_BLEND_TRUSTED_SAMPLE_COUNT = 20
SECTOR_BLEND_MAX_ROLE_WEIGHT = Decimal("0.85")

# Sector nominal salary is published quarterly; tolerate a few quarters of
# publication/sync lag before treating a cached figure as too stale to use.
MAX_STALE_QUARTERS = 3


def _get_experience_percentile(months):
    for threshold, value in reversed(EXPERIENCE_PERCENTILES):
        if months >= threshold:
            return value
    return EXPERIENCE_PERCENTILES[0][1]


def _get_candidate_experience_months(resume):
    experiences = resume.experiences.all()
    intervals = [
        (exp.start_date, exp.end_date)
        for exp in experiences
        if exp.start_date
    ]
    return calculate_total_experience_months(intervals)


def _interpolate_market_percentile(median, salary_from, salary_to, target_pct):
    """
    Piecewise-linear interpolation across the three points the market
    aggregate gives us: salary_from ~p10, median ~p50, salary_to ~p90.
    Beyond p90 this extrapolates using the p50->p90 slope, which is what
    lets a senior/expert percentile target sit above the sample's observed
    range instead of being clamped to it.
    """
    if target_pct <= _P50:
        low, low_pct = (salary_from, _P10) if salary_from is not None else (median, _P50)
        span = _P50 - low_pct
        if span <= 0:
            return median
        ratio = (target_pct - low_pct) / span
        return low + (median - low) * ratio

    high, high_pct = (salary_to, _P90) if salary_to is not None else (median, _P50)
    span = high_pct - _P50
    if span <= 0:
        return median
    ratio = (target_pct - _P50) / span
    return median + (high - median) * ratio


def _period_ordinal(period_label):
    try:
        year_str, quarter_str = period_label.split("-Q")
        return int(year_str) * 4 + int(quarter_str)
    except (ValueError, AttributeError):
        return None


def _is_period_stale(period_label, now=None):
    ordinal = _period_ordinal(period_label)
    if ordinal is None:
        return True
    now = now or timezone.now()
    current_ordinal = now.year * 4 + ((now.month - 1) // 3 + 1)
    return (current_ordinal - ordinal) > MAX_STALE_QUARTERS


def _resolve_domain(target_role):
    """
    Deliberately derives the sector-lookup domain from target_role text
    rather than resume.domain: the latter can be mis-assigned (candidate
    self-select or AI resume generation can get it wrong), and trusting it
    would anchor the estimate to the wrong sector's nominal salary -- worse
    than not anchoring at all. target_role is the same text already used to
    query HH/platform market data, so this keeps a single source of truth
    for "what are we calculating a salary for" instead of a second,
    independently-fallible one.
    """
    from apps.resumes.services.resume_generation import DomainMatcher

    match = DomainMatcher.find_matching_domain(target_role)
    if not match:
        return None

    from apps.domain.models import Domain

    return Domain.objects.filter(id=match["id"]).first()


def _get_sector_reference(target_role):
    """
    Latest stat.uz nominal salary for the sector implied by target_role, or
    None if it doesn't resolve to a domain, that domain has no sector
    classification yet, or the figure on file is too old to trust. Never
    raises: a lookup failure here should degrade to the role-only estimate,
    not break the calculator.
    """
    try:
        domain = _resolve_domain(target_role)
        if not domain or not domain.sector_code:
            return None

        from apps.general.services.stat_uz_sector_salary import get_latest_sector_salary

        reference = get_latest_sector_salary(domain.sector_code)
        if not reference or _is_period_stale(reference["period_label"]):
            return None
        return reference
    except Exception:
        logger.warning("Failed to resolve sector reference for role=%s", target_role, exc_info=True)
        return None


def _blend_with_sector(median, salary_from, salary_to, sample_count, sector_nominal):
    """
    Anchor the role-level distribution's scale toward the stat.uz sector
    nominal salary, weighted by how much role-level sample we have, while
    keeping the distribution's relative shape (the ratio between its
    from/median/to points) intact.
    """
    if sector_nominal is None or median is None or median <= 0:
        return median, salary_from, salary_to

    alpha = min(
        SECTOR_BLEND_MAX_ROLE_WEIGHT,
        Decimal(sample_count) / Decimal(SECTOR_BLEND_TRUSTED_SAMPLE_COUNT),
    )
    blended_median = (alpha * median + (1 - alpha) * sector_nominal).quantize(Decimal("0.01"))
    scale = blended_median / median

    blended_from = (salary_from * scale).quantize(Decimal("0.01")) if salary_from is not None else None
    blended_to = (salary_to * scale).quantize(Decimal("0.01")) if salary_to is not None else None
    return blended_median, blended_from, blended_to


def calculate_salary(candidate, resume, target_role):
    """
    Calculate current salary, potential salary, and market match.

    current_salary / potential_salary are read off a market distribution
    whose *shape* comes from HH + platform vacancy data (median plus
    p10/p90 range) and whose *scale* is anchored toward the stat.uz sector
    nominal salary when the role-level sample is thin -- so a niche or
    small-sample role query can't produce an artificially low ceiling the
    way a flat coefficient-of-median model could.

    Returns dict with:
      - current_salary: market percentile position for the candidate's experience
      - potential_salary: a percentile band above current (achievable upside)
      - market_median: the (possibly sector-blended) median used for the calc
      - match_percentage: (current_salary / market_median) * 100
      - experience_months: total experience in months
      - sample_count: role-level data points backing the estimate
      - sector_reference_salary / sector_reference_period: the stat.uz figure
        used to anchor the estimate, if any, for transparency
      - currency: always 'UZS'
    """
    market = get_market_salary_for_role(target_role)
    if market is None:
        logger.warning("No market data for role=%s", target_role)
        return {"error": "insufficient_data"}

    median = market["median_salary_uzs"]
    salary_from = market.get("salary_from")
    salary_to = market.get("salary_to")
    sample_count = market.get("sample_count", 0)

    sector_reference = _get_sector_reference(target_role)
    sector_nominal = sector_reference["avg_salary_uzs"] if sector_reference else None

    median, salary_from, salary_to = _blend_with_sector(
        median, salary_from, salary_to, sample_count, sector_nominal
    )

    experience_months = _get_candidate_experience_months(resume)
    current_pct = _get_experience_percentile(experience_months)
    potential_pct = min(current_pct + POTENTIAL_PERCENTILE_UPLIFT, MAX_PERCENTILE)

    current_salary = _interpolate_market_percentile(
        median, salary_from, salary_to, current_pct
    ).quantize(Decimal("0.01"))
    potential_salary = _interpolate_market_percentile(
        median, salary_from, salary_to, potential_pct
    ).quantize(Decimal("0.01"))

    match_percentage = Decimal("0.0")
    if median is not None and median > 0:
        match_percentage = ((current_salary / median) * 100).quantize(Decimal("0.1"))

    result = {
        "current_salary": str(current_salary),
        "potential_salary": str(potential_salary),
        "market_median": str(median.quantize(Decimal("0.01"))),
        "match_percentage": str(match_percentage),
        "experience_months": experience_months,
        "sample_count": sample_count,
        "currency": "UZS",
        "sector_reference_salary": (
            str(sector_nominal.quantize(Decimal("0.01"))) if sector_nominal is not None else None
        ),
        "sector_reference_period": sector_reference["period_label"] if sector_reference else None,
    }
    return result
