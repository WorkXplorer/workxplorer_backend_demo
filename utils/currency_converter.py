"""
Currency conversion utilities for salary filtering.

Provides functions to convert salary values between currencies using
exchange rates from the Central Bank of Uzbekistan (CBU).
All conversions go through UZS as the intermediate currency.

Default currency is UZS when not specified.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from django.db.models import QuerySet, Q

logger = logging.getLogger(__name__)


# Default currency when none is specified
DEFAULT_CURRENCY = "UZS"

# Whitelist of supported currency codes
ALLOWED_CURRENCIES = {"UZS", "USD", "EUR", "RUB"}


def _get_rate_to_uzs(currency_code: str) -> Optional[float]:
    """
    Get exchange rate for 1 unit of currency in UZS.
    Lazy import to avoid circular imports.
    """
    from apps.general.currency.fetcher import get_rate_to_uzs
    return get_rate_to_uzs(currency_code)


def convert_to_uzs(amount: Decimal, from_currency: str) -> Optional[Decimal]:
    """
    Convert an amount from a given currency to UZS.

    Args:
        amount: The amount to convert.
        from_currency: Source currency code (USD, EUR, UZS).

    Returns:
        Amount in UZS, or None if conversion fails.
    """
    if amount is None:
        return None

    from_currency = (from_currency or DEFAULT_CURRENCY).upper().strip()

    # Validate against allowed currencies to prevent injection
    if from_currency not in ALLOWED_CURRENCIES:
        logger.warning("Rejected invalid source currency code: %s", from_currency)
        return None

    if from_currency == "UZS":
        return amount

    rate = _get_rate_to_uzs(from_currency)
    if rate is None:
        logger.warning("Cannot convert from %s: rate unavailable", from_currency)
        return None

    return amount * Decimal(str(rate))


def convert_from_uzs(amount_uzs: Decimal, to_currency: str) -> Optional[Decimal]:
    """
    Convert an amount from UZS to a target currency.

    Args:
        amount_uzs: Amount in UZS.
        to_currency: Target currency code.

    Returns:
        Amount in target currency, or None if conversion fails.
    """
    if amount_uzs is None:
        return None

    to_currency = (to_currency or DEFAULT_CURRENCY).upper().strip()

    # Validate against allowed currencies to prevent injection
    if to_currency not in ALLOWED_CURRENCIES:
        logger.warning("Rejected invalid target currency code: %s", to_currency)
        return None

    if to_currency == "UZS":
        return amount_uzs

    rate = _get_rate_to_uzs(to_currency)
    if rate is None or rate == 0:
        logger.warning("Cannot convert to %s: rate unavailable or zero", to_currency)
        return None

    return amount_uzs / Decimal(str(rate))


def convert_amount(
        amount: Decimal,
        from_currency: str,
        to_currency: str,
) -> Optional[Decimal]:
    """
    Convert an amount between any two supported currencies.

    Goes through UZS as the intermediate currency.

    Args:
        amount: The amount to convert.
        from_currency: Source currency code.
        to_currency: Target currency code.

    Returns:
        Converted amount, or None if conversion fails.
    """
    if amount is None:
        return None

    from_currency = (from_currency or DEFAULT_CURRENCY).upper().strip()
    to_currency = (to_currency or DEFAULT_CURRENCY).upper().strip()

    if from_currency == to_currency:
        return amount

    # Convert to UZS first
    amount_uzs = convert_to_uzs(amount, from_currency)
    if amount_uzs is None:
        return None

    # Convert from UZS to target
    return convert_from_uzs(amount_uzs, to_currency)


def get_salary_range_in_uzs(
        salary_min: Optional[str],
        salary_max: Optional[str],
        currency: Optional[str],
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Parse and convert salary range params to UZS.

    Args:
        salary_min: Minimum salary as string.
        salary_max: Maximum salary as string.
        currency: Currency code for the salary values. Defaults to UZS.

    Returns:
        Tuple of (min_uzs, max_uzs). Either may be None.
    """
    currency = (currency or DEFAULT_CURRENCY).upper().strip()
    min_uzs = None
    max_uzs = None

    if salary_min:
        try:
            min_val = Decimal(salary_min)
            min_uzs = convert_to_uzs(min_val, currency)
        except (InvalidOperation, ValueError, TypeError):
            # Invalid salary_min format - skip conversion and leave as None
            pass

    if salary_max:
        try:
            max_val = Decimal(salary_max)
            max_uzs = convert_to_uzs(max_val, currency)
        except (InvalidOperation, ValueError, TypeError):
            # Invalid salary_max format - skip conversion and leave as None
            pass

    return min_uzs, max_uzs


def _parse_salary_bounds(
        salary_min: Optional[str],
        salary_max: Optional[str],
        currency: Optional[str],
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[str]]:
    """
    Parse salary bounds and normalize currency.

    Returns:
        Tuple(min_val, max_val, normalized_currency). Currency is None if invalid.
    """
    normalized_currency = (currency or DEFAULT_CURRENCY).upper().strip()
    if normalized_currency not in ALLOWED_CURRENCIES:
        return None, None, None

    try:
        min_val = Decimal(salary_min) if salary_min else None
    except (InvalidOperation, ValueError, TypeError):
        min_val = None

    try:
        max_val = Decimal(salary_max) if salary_max else None
    except (InvalidOperation, ValueError, TypeError):
        max_val = None

    return min_val, max_val, normalized_currency


def _build_currency_conditions(
        min_val: Optional[Decimal],
        max_val: Optional[Decimal],
        source_currency: str,
        currency_field: str,
        min_field: str,
        max_field: str,
        extra_q: Optional[Q] = None,
) -> Q:
    """
    Build OR-combined Q conditions by converting filter bounds per target currency.
    """
    target_currencies = ("UZS", "USD", "EUR")
    q_conditions = Q()

    for target_cur in target_currencies:
        converted_min = (
            convert_amount(min_val, source_currency, target_cur)
            if min_val is not None
            else None
        )
        converted_max = (
            convert_amount(max_val, source_currency, target_cur)
            if max_val is not None
            else None
        )

        if min_val is not None and converted_min is None:
            continue
        if max_val is not None and converted_max is None:
            continue

        cur_q = Q(**{currency_field: target_cur})
        if extra_q is not None:
            cur_q &= extra_q
        if converted_min is not None:
            cur_q &= Q(**{f"{max_field}__gte": converted_min})
        if converted_max is not None:
            cur_q &= Q(**{f"{min_field}__lte": converted_max})

        q_conditions |= cur_q

    return q_conditions


def filter_vacancies_by_salary(
        queryset: QuerySet,
        salary_min: Optional[str],
        salary_max: Optional[str],
        currency: Optional[str],
) -> QuerySet:
    """
    Filter vacancy queryset by salary range with currency conversion.

    Converts the filter values to each vacancy's own currency for comparison,
    avoiding any change to stored data. Uses a single pass through the
    queryset by building Q objects for each supported currency.

    Args:
        queryset: Base vacancy queryset.
        salary_min: Minimum salary filter value (as string).
        salary_max: Maximum salary filter value (as string).
        currency: Currency of the filter values. Defaults to UZS.

    Returns:
        Filtered queryset.
    """
    if not salary_min and not salary_max:
        return queryset

    min_val, max_val, normalized_currency = _parse_salary_bounds(
        salary_min, salary_max, currency
    )
    if normalized_currency is None:
        return queryset

    if min_val is None and max_val is None:
        return queryset

    q_conditions = _build_currency_conditions(
        min_val=min_val,
        max_val=max_val,
        source_currency=normalized_currency,
        currency_field="salary_currency",
        min_field="salary_min",
        max_field="salary_max",
    )

    # Include vacancies with NULL salary (negotiable salaries)
    # These are considered relevant regardless of the salary filter
    null_salary_condition = Q(salary_min__isnull=True) | Q(salary_max__isnull=True)

    if q_conditions:
        queryset = queryset.filter(q_conditions | null_salary_condition)
    else:
        queryset = queryset.filter(null_salary_condition)

    return queryset


def filter_resumes_by_salary(
        queryset: QuerySet,
        salary_min: Optional[str],
        salary_max: Optional[str],
        currency: Optional[str],
) -> QuerySet:
    """
    Filter resume queryset by current_salary with currency conversion.

    Converts filter values to each resume's own salary_currency for comparison.
    Excludes resumes where salary_hide is True.

    Args:
        queryset: Base resume queryset.
        salary_min: Minimum salary filter value (as string).
        salary_max: Maximum salary filter value (as string).
        currency: Currency of the filter values. Defaults to UZS.

    Returns:
        Filtered queryset.
    """
    if not salary_min and not salary_max:
        return queryset

    # Exclude resumes where salary is hidden from recruiter views
    queryset = queryset.exclude(salary_hide=True)

    min_val, max_val, normalized_currency = _parse_salary_bounds(
        salary_min, salary_max, currency
    )
    if normalized_currency is None:
        return queryset

    if min_val is None and max_val is None:
        return queryset

    q_conditions = _build_currency_conditions(
        min_val=min_val,
        max_val=max_val,
        source_currency=normalized_currency,
        currency_field="salary_currency",
        min_field="current_salary",
        max_field="current_salary",
    )

    # When salary_min is specified, exclude candidates with null salary
    # (they don't meet the minimum salary requirement).
    # When only salary_max is specified, include null salary candidates.
    include_null_salary = min_val is None

    if q_conditions:
        if include_null_salary:
            null_salary_condition = Q(current_salary__isnull=True)
            queryset = queryset.filter(q_conditions | null_salary_condition)
        else:
            queryset = queryset.filter(q_conditions)
    elif include_null_salary:
        null_salary_condition = Q(current_salary__isnull=True)
        queryset = queryset.filter(null_salary_condition)

    return queryset


def filter_applications_by_resume_salary(
        queryset: QuerySet,
        salary_min: Optional[str],
        salary_max: Optional[str],
        currency: Optional[str],
) -> QuerySet:
    """
    Filter application queryset by the candidate's resume salary with currency conversion.

    Uses the resume_used relationship to filter by current_salary/salary_currency.
    Excludes applications where the resume has salary_hide=True.

    Args:
        queryset: Base JobApplication queryset.
        salary_min: Minimum salary filter value (as string).
        salary_max: Maximum salary filter value (as string).
        currency: Currency of the filter values. Defaults to UZS.

    Returns:
        Filtered queryset.
    """
    if not salary_min and not salary_max:
        return queryset

    # Exclude applications where resume salary is hidden
    queryset = queryset.exclude(resume_used__salary_hide=True)

    min_val, max_val, normalized_currency = _parse_salary_bounds(
        salary_min, salary_max, currency
    )
    if normalized_currency is None:
        return queryset

    if min_val is None and max_val is None:
        return queryset

    q_conditions = _build_currency_conditions(
        min_val=min_val,
        max_val=max_val,
        source_currency=normalized_currency,
        currency_field="resume_used__salary_currency",
        min_field="resume_used__current_salary",
        max_field="resume_used__current_salary",
        extra_q=~Q(resume_used__current_salary=0),
    )

    # Only include applications with null salary when salary_min is not specified
    # (null salary candidates are only relevant when there's no minimum requirement)
    # When a salary range is specified, exclude null/0 salary candidates
    if q_conditions:
        if min_val is None:
            # No minimum specified - include null salary candidates
            null_salary_condition = Q(resume_used__current_salary__isnull=True)
            queryset = queryset.filter(q_conditions | null_salary_condition)
        else:
            # Minimum specified - only include candidates with salary in range
            queryset = queryset.filter(q_conditions)
    else:
        # No valid conditions - return empty queryset
        queryset = queryset.none()

    return queryset
