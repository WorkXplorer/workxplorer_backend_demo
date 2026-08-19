"""
Helper functions for status-based analytics queries.

This module provides utilities for querying applications by status category,
supporting both the legacy CharField status and the new FK-based status system.

The key insight: Analytics need to query by category (HIRED, SCREENING, etc.)
not by specific status keys, since companies can have custom status names.
"""

from typing import List, Set
from functools import lru_cache

from django.db.models import Q

from apps.applications.models import StatusCategory, ApplicationStatusModel


@lru_cache(maxsize=16)
def get_status_keys_for_category(category_key: str, company_id=None) -> Set[str]:
    """
    Get all status keys that belong to a specific analytics category.
    
    This function is cached because category mappings don't change frequently.
    Use clear_status_cache() when statuses are created/updated.
    
    Args:
        category_key: Analytics category key (e.g., 'HIRED', 'SCREENING')
        company_id: Optional company ID to filter by. If None, returns all.
        
    Returns:
        Set of status keys (e.g., {'OFFER_ACCEPTED', 'HIRED'})
    """
    qs = ApplicationStatusModel.objects.filter(
        category__key=category_key,
        is_active=True,
    )
    
    if company_id:
        qs = qs.filter(company_id=company_id)
    
    return set(qs.values_list('key', flat=True))


def clear_status_cache():
    """Clear the status cache when statuses are modified."""
    get_status_keys_for_category.cache_clear()


def get_hired_status_keys(company_id=None) -> Set[str]:
    """
    Get all status keys that represent 'hired' candidates.

    Returns keys from the HIRED analytics category, plus the legacy
    OFFER_ACCEPTED string for backwards compatibility with applications
    created before the flexible status system was deployed.
    """
    keys = get_status_keys_for_category(StatusCategory.HIRED, company_id)
    # Legacy: applications may still carry the hardcoded OFFER_ACCEPTED string
    keys.add('OFFER_ACCEPTED')
    return keys


def get_screening_status_keys(company_id=None) -> Set[str]:
    """Get all status keys in the SCREENING category."""
    return get_status_keys_for_category(StatusCategory.SCREENING, company_id)


def get_interviewing_status_keys(company_id=None) -> Set[str]:
    """Get all status keys in the INTERVIEWING category."""
    return get_status_keys_for_category(StatusCategory.INTERVIEWING, company_id)


def get_offered_status_keys(company_id=None) -> Set[str]:
    """Get all status keys in the OFFERED category."""
    return get_status_keys_for_category(StatusCategory.OFFERED, company_id)


def get_rejected_status_keys(company_id=None) -> Set[str]:
    """Get all status keys in the REJECTED category."""
    return get_status_keys_for_category(StatusCategory.REJECTED, company_id)


def build_status_category_filter(
    category_keys: List[str],
    company_id=None,
    status_field: str = 'status'
) -> Q:
    """
    Build a Django Q object for filtering applications by status categories.
    
    Args:
        category_keys: List of category keys to include
        company_id: Optional company ID to filter by
        status_field: Name of the status field on the model (default: 'status')
        
    Returns:
        Q object for filtering
        
    Example:
        # Filter applications that are in SCREENING or INTERVIEWING categories
        filter_q = build_status_category_filter(['SCREENING', 'INTERVIEWING'])
        applications = Application.objects.filter(filter_q)
    """
    all_keys = set()
    for category_key in category_keys:
        all_keys.update(get_status_keys_for_category(category_key, company_id))
    
    if not all_keys:
        # Return a Q object that matches nothing
        return Q(pk__in=[])
    
    return Q(**{f'{status_field}__in': all_keys})


# Pre-defined category groups for common analytics queries

# All statuses that indicate an invitation was sent (screening phase and beyond)
INVITED_CATEGORIES = [
    StatusCategory.SCREENING,
    StatusCategory.INTERVIEWING,
    StatusCategory.ASSESSMENT,
    StatusCategory.TRAINING,
    StatusCategory.OFFERED,
    StatusCategory.HIRED,
]

# All statuses that indicate a candidate progressed past initial screening
INTERVIEWED_CATEGORIES = [
    StatusCategory.INTERVIEWING,
    StatusCategory.ASSESSMENT,
    StatusCategory.TRAINING,
    StatusCategory.OFFERED,
    StatusCategory.HIRED,
]

# All statuses that indicate an offer was made
OFFER_CATEGORIES = [
    StatusCategory.OFFERED,
    StatusCategory.HIRED,
    StatusCategory.OFFER_REJECTED,
]


def get_invited_status_keys(company_id=None) -> Set[str]:
    """
    Get status keys for candidates who were invited to next stages.
    
    This includes anyone who progressed beyond APPLIED:
    - SCREENING (e.g., INTERVIEW_SCHEDULED)
    - INTERVIEWING (e.g., INTERVIEWED)
    - OFFERED
    - HIRED
    """
    keys = set()
    for category in INVITED_CATEGORIES:
        keys.update(get_status_keys_for_category(category, company_id))
    return keys


def get_interviewed_status_keys(company_id=None) -> Set[str]:
    """
    Get status keys for candidates who were actually interviewed.
    
    This includes:
    - INTERVIEWING (e.g., INTERVIEWED)
    - OFFERED
    - HIRED
    """
    keys = set()
    for category in INTERVIEWED_CATEGORIES:
        keys.update(get_status_keys_for_category(category, company_id))
    return keys


def get_offer_extended_status_keys(company_id=None) -> Set[str]:
    """
    Get status keys for candidates who received an offer.

    This includes:
    - OFFERED
    - HIRED (offer accepted)
    - OFFER_REJECTED (offer declined by candidate)
    """
    keys: Set[str] = set()
    keys.update(get_status_keys_for_category(StatusCategory.OFFERED, company_id))
    keys.update(get_status_keys_for_category(StatusCategory.HIRED, company_id))
    keys.update(get_status_keys_for_category(StatusCategory.OFFER_REJECTED, company_id))
    return keys
