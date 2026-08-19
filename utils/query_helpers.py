"""
Query helper utilities for the WorkXplorer platform.

This module provides reusable query logic to avoid code duplication
and ensure consistency across views.
"""

from django.db.models import Q


def get_candidate_ids_by_skills(skills_list: list[str], company) -> list:
    """
    Get candidate IDs who have resumes with the specified skills.
    
    Uses a single optimized query with OR conditions instead of N queries.
    
    Args:
        skills_list: List of skill names to search for (case-insensitive)
        company: Company object to filter candidates by
    
    Returns:
        List of candidate IDs that match the skills criteria.
        Empty list if no candidates found.
    
    Example:
        skills = ["Python", "Django", "React"]
        candidate_ids = get_candidate_ids_by_skills(skills, my_company)
        applications = JobApplication.objects.filter(candidate__id__in=candidate_ids)
    """
    from apps.resumes.models import Resume

    if not skills_list:
        return []

    # Build OR query for all skills at once (single DB query)
    skill_q = Q()
    for skill_name in skills_list:
        skill_q |= Q(skills__name__icontains=skill_name)

    # Execute single query with OR conditions
    candidate_ids = Resume.objects.filter(
        candidate__applications__vacancy__company=company
    ).filter(skill_q).values_list('candidate_id', flat=True).distinct()

    return list(candidate_ids)
