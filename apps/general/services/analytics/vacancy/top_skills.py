"""
Top candidate skills data for vacancy analytics.
Collects skill occurrence counts among candidates who applied to a vacancy.

Note: We only send raw counts. Calculations (percentages) are done by the analytics service.
"""

from typing import Any, Dict
from collections import Counter

from apps.applications.models import JobApplication as Application
from apps.resumes.models import Resume


def calculate_vacancy_top_skills(vacancy_id: str, limit: int = 5) -> Dict[str, Any]:
    """
    Calculate top skills among candidates who applied to a specific vacancy.
    
    Logic:
    1. Get all candidates who applied to this vacancy
    2. Get their resumes (main resume or any resume with skills)
    3. Count skill occurrences across all candidates
    4. Return top N skills with their occurrence counts
    
    Args:
        vacancy_id: UUID string of the vacancy
        limit: Number of top skills to return (default: 5)
        
    Returns:
        Dictionary with:
        - total_candidates: number of candidates with skills data
        - skills: list of top skills with id, name, and count
    """
    # Get candidate IDs who applied to this vacancy
    candidate_ids = list(
        Application.objects.filter(
            vacancy_id=vacancy_id
        ).values_list('candidate_id', flat=True).distinct()
    )

    if not candidate_ids:
        return {
            "total_candidates": 0,
            "total_candidates_with_skills": 0,
            "skills": [],
        }

    # Get resumes for these candidates (prefer main resume, but include others)
    # First try to get main resumes
    resumes = Resume.objects.filter(
        candidate_id__in=candidate_ids
    ).prefetch_related('resume_skills__skill')

    # Count skills across all resumes
    skill_counter = Counter()
    skill_names = {}  # skill_id -> skill_name mapping
    candidates_with_skills = set()

    for resume in resumes:
        resume_skill_ids = set()
        for resume_skill in resume.resume_skills.all():
            skill = resume_skill.skill
            skill_id = str(skill.id)

            # Only count each skill once per candidate (not per resume)
            if skill_id not in resume_skill_ids:
                resume_skill_ids.add(skill_id)
                skill_counter[skill_id] += 1
                skill_names[skill_id] = skill.name

        if resume_skill_ids:
            candidates_with_skills.add(resume.candidate_id)

    # Get top N skills
    top_skills = skill_counter.most_common(limit)

    skills_list = [
        {
            "skill_id": skill_id,
            "skill_name": skill_names[skill_id],
            "candidates_count": count,
        }
        for skill_id, count in top_skills
    ]

    return {
        "total_candidates": len(candidate_ids),
        "total_candidates_with_skills": len(candidates_with_skills),
        "skills": skills_list,
    }
