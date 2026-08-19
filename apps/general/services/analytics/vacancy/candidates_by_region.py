"""
Candidates by region metric for a vacancy.

Calculates the distribution of candidates who applied to a specific vacancy
across all regions of Uzbekistan, including:
- Number of candidates per region
- Average age of candidates per region
- Breakdown of candidates by educational partner (university) per region

Even regions with 0 candidates are included.
"""
from typing import Any, Dict, List
from datetime import date

from django.utils import timezone

from apps.applications.models import JobApplication

# All regions in Uzbekistan with their codes and display names
# Sourced from CandidateProfile.RegionChoices
UZBEKISTAN_REGIONS: List[Dict[str, str]] = [
    {"code": "Andijon", "name": "Andijon"},
    {"code": "Buxoro", "name": "Buxoro"},
    {"code": "Jizzax", "name": "Jizzax"},
    {"code": "Qashqadaryo", "name": "Qashqadaryo"},
    {"code": "Navoiy", "name": "Navoiy"},
    {"code": "Namangan", "name": "Namangan"},
    {"code": "Samarqand", "name": "Samarqand"},
    {"code": "Sirdaryo", "name": "Sirdaryo"},
    {"code": "Surxondaryo", "name": "Surxondaryo"},
    {"code": "Toshkent shahar", "name": "Toshkent shahar"},
    {"code": "Toshkent viloyati", "name": "Toshkent viloyati"},
    {"code": "Farg'ona", "name": "Farg'ona"},
    {"code": "Xorazm", "name": "Xorazm"},
]


def _calculate_age(date_of_birth: date) -> int:
    """Calculate age from date of birth."""
    if not date_of_birth:
        return None
    today = timezone.now().date()
    age = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        age -= 1
    return age if age >= 0 else None


def _get_candidates_for_vacancy(vacancy_id: str) -> List[Dict[str, Any]]:
    """
    Get all candidates who applied to a vacancy with their profile data.
    
    Returns a list of dicts with candidate info including:
    - id: candidate ID
    - address: region
    - edupartner_name: educational partner name
    - date_of_birth: for age calculation
    """
    applications = JobApplication.objects.filter(
        vacancy_id=vacancy_id
    ).select_related(
        'candidate__candidateprofile',
        'candidate__edupartner'
    ).values(
        'candidate__candidateprofile__region',
        'candidate__edupartner__name',
        'candidate__date_of_birth',
        'candidate__id'
    ).distinct()

    candidates = []
    for app in applications:
        candidates.append({
            'id': app['candidate__id'],
            'address': app['candidate__candidateprofile__region'],  # Updated to use region field
            'edupartner_name': app['candidate__edupartner__name'] or 'Unknown',
            'date_of_birth': app['candidate__date_of_birth'],
        })

    return candidates


def _get_edupartners_for_region(candidates: List[Dict[str, Any]], region_code: str) -> Dict[str, int]:
    """
    Get edupartner breakdown for a specific region.

    Returns a dict mapping edupartner_name -> count
    """
    region_candidates = [c for c in candidates if c['address'] == region_code]  # Updated to use address key for region
    edupartner_counts: Dict[str, int] = {}

    for candidate in region_candidates:
        edu_name = candidate['edupartner_name']
        edupartner_counts[edu_name] = edupartner_counts.get(edu_name, 0) + 1

    return edupartner_counts


def _calculate_average_age_for_candidates(candidates: List[Dict[str, Any]]) -> float:
    """Calculate average age of candidates with known birth dates."""
    ages = []
    for candidate in candidates:
        age = _calculate_age(candidate['date_of_birth'])
        if age is not None:
            ages.append(age)

    if not ages:
        return 0.0

    return sum(ages) / len(ages)


def calculate_vacancy_candidates_by_region(vacancy_id: str) -> Dict[str, Any]:
    """
    Calculate candidate distribution by region for a specific vacancy.

    Groups candidates who applied to the vacancy by their address (region)
    and further breaks down by educational partner (university).
    All 13 regions of Uzbekistan are always returned, even if count is 0.

    Args:
        vacancy_id: UUID string of the vacancy

    Returns:
        Dictionary containing:
        - total_candidates: Total number of candidates who applied
        - candidates_with_region: Number of candidates with known region
        - average_age: Average age of all candidates
        - regions: List of all regions with their candidate counts,
                   average age, and edupartner breakdown
    """
    # Get all candidates who applied to this vacancy
    candidates = _get_candidates_for_vacancy(vacancy_id)

    total_candidates = len(candidates)

    # Count candidates with known region
    candidates_with_region = len([c for c in candidates if c['address']])  # Updated to use address key for region

    # Calculate overall average age
    overall_average_age = _calculate_average_age_for_candidates(candidates)

    # Build the result with all regions (including those with 0 candidates)
    regions_data: List[Dict[str, Any]] = []

    for region in UZBEKISTAN_REGIONS:
        region_code = region["code"]
        region_name = region["name"]

        # Get candidates for this region
        region_candidates = [c for c in candidates if c['address'] == region_code]  # Updated to use address key for region
        region_count = len(region_candidates)

        # Calculate average age for this region
        region_average_age = _calculate_average_age_for_candidates(region_candidates)

        # Get edupartner breakdown for this region
        edupartner_counts = _get_edupartners_for_region(candidates, region_code)

        # Build edupartner list (sorted by count descending, then by name)
        edupartners_list = [
            {"edupartner_name": name, "count": count}
            for name, count in sorted(
                edupartner_counts.items(),
                key=lambda x: (-x[1], x[0])
            )
        ]

        regions_data.append({
            "region_code": region_code,
            "region_name": region_name,
            "candidates_count": region_count,
            "average_age": region_average_age,
            "edupartners": edupartners_list,
        })

    return {
        "total_candidates": total_candidates,
        "candidates_with_region": candidates_with_region,
        "average_age": overall_average_age,
        "regions": regions_data,
    }
