"""
Skill Matching Service for comparing vacancy and resume skills.

This service provides optimized skill matching functionality for:
- Candidates: Compare their resume skills with vacancy requirements
- Recruiters: Compare each applicant's skills with vacancy requirements

Performance optimized with set operations and minimal database queries.
"""

from typing import Optional
from dataclasses import dataclass, field


@dataclass
class SkillInfo:
    """Represents a skill with its metadata."""
    skill_id: int
    skill_name: str
    is_required: bool = True
    proficiency_level: str = "UNDEFINED"
    minimum_years: int = 0


@dataclass
class MatchedSkill:
    """Represents a matched skill between vacancy and resume."""
    skill_id: int
    skill_name: str
    is_required: bool
    candidate_level: str
    required_level: str
    candidate_years: int = 0
    required_years: int = 0


@dataclass
class MissingSkill:
    """Represents a skill required by vacancy but missing from resume."""
    skill_id: int
    skill_name: str
    is_required: bool
    required_level: str
    required_years: int = 0


@dataclass
class SkillMatchResult:
    """Result of skill matching between vacancy and resume."""
    matched_skills: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    match_percentage: float = 0.0
    total_vacancy_skills: int = 0
    total_required_skills: int = 0
    matched_required_skills: int = 0
    matched_total_skills: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "matched_skills": [
                {
                    "skill_id": s.skill_id,
                    "skill_name": s.skill_name,
                    "is_required": s.is_required,
                    "candidate_level": s.candidate_level,
                    "required_level": s.required_level,
                    "candidate_years": s.candidate_years,
                    "required_years": s.required_years,
                }
                for s in self.matched_skills
            ],
            "missing_skills": [
                {
                    "skill_id": s.skill_id,
                    "skill_name": s.skill_name,
                    "is_required": s.is_required,
                    "required_level": s.required_level,
                    "required_years": s.required_years,
                }
                for s in self.missing_skills
            ],
            "match_percentage": round(self.match_percentage, 1),
            "total_vacancy_skills": self.total_vacancy_skills,
            "total_required_skills": self.total_required_skills,
            "matched_required_skills": self.matched_required_skills,
            "matched_total_skills": self.matched_total_skills,
        }


class SkillMatcherService:
    """
    Service for matching skills between vacancies and resumes.
    
    This service uses optimized set operations for fast skill comparison.
    It supports both single candidate matching and bulk matching for
    recruiter views.
    
    Usage:
        # Single match (candidate view)
        result = SkillMatcherService.get_skill_match(vacancy, resume)
        
        # Bulk match (recruiter view)
        results = SkillMatcherService.bulk_get_skill_match(vacancy, applications)
    """

    @staticmethod
    def get_vacancy_skills(vacancy) -> dict[int, SkillInfo]:
        """
        Extract skills from vacancy with their requirements.
        
        Args:
            vacancy: Vacancy instance (should have vacancyskill_set prefetched)
            
        Returns:
            Dictionary mapping skill_id to SkillInfo
        """
        skills = {}
        
        # Use prefetched data if available, otherwise query
        vacancy_skills = vacancy.vacancyskill_set.all()
        
        for vs in vacancy_skills:
            skills[vs.skill_id] = SkillInfo(
                skill_id=vs.skill_id,
                skill_name=vs.skill.name,
                is_required=vs.is_required,
                proficiency_level=vs.proficiency_level or "UNDEFINED",
                minimum_years=vs.minimum_years or 0,
            )
        
        return skills

    @staticmethod
    def get_resume_skills(resume) -> dict[int, SkillInfo]:
        """
        Extract skills from resume with proficiency levels.
        
        Args:
            resume: Resume instance (should have resume_skills prefetched)
            
        Returns:
            Dictionary mapping skill_id to SkillInfo
        """
        if resume is None:
            return {}
            
        skills = {}
        
        # Use prefetched data if available
        resume_skills = resume.resume_skills.all()
        
        for rs in resume_skills:
            skills[rs.skill_id] = SkillInfo(
                skill_id=rs.skill_id,
                skill_name=rs.skill.name,
                is_required=False,  # Not applicable for resume skills
                proficiency_level=rs.proficiency_level or "UNDEFINED",
                minimum_years=rs.minimum_years or 0,
            )
        
        return skills

    @staticmethod
    def calculate_match(
        vacancy_skills: dict[int, SkillInfo],
        resume_skills: dict[int, SkillInfo]
    ) -> SkillMatchResult:
        """
        Calculate skill match between vacancy requirements and resume skills.
        
        Uses set operations for O(n) complexity.
        
        Args:
            vacancy_skills: Dictionary of vacancy skill requirements
            resume_skills: Dictionary of resume skills
            
        Returns:
            SkillMatchResult with matched/missing skills and percentages
        """
        result = SkillMatchResult()
        
        if not vacancy_skills:
            return result
        
        # Get skill ID sets for fast comparison
        vacancy_skill_ids = set(vacancy_skills.keys())
        resume_skill_ids = set(resume_skills.keys())
        
        # Find matched and missing skills using set operations
        matched_ids = vacancy_skill_ids & resume_skill_ids
        missing_ids = vacancy_skill_ids - resume_skill_ids
        
        # Build matched skills list
        for skill_id in matched_ids:
            vacancy_skill = vacancy_skills[skill_id]
            resume_skill = resume_skills[skill_id]
            
            result.matched_skills.append(MatchedSkill(
                skill_id=skill_id,
                skill_name=vacancy_skill.skill_name,
                is_required=vacancy_skill.is_required,
                candidate_level=resume_skill.proficiency_level,
                required_level=vacancy_skill.proficiency_level,
                candidate_years=resume_skill.minimum_years,
                required_years=vacancy_skill.minimum_years,
            ))
        
        # Build missing skills list
        for skill_id in missing_ids:
            vacancy_skill = vacancy_skills[skill_id]
            
            result.missing_skills.append(MissingSkill(
                skill_id=skill_id,
                skill_name=vacancy_skill.skill_name,
                is_required=vacancy_skill.is_required,
                required_level=vacancy_skill.proficiency_level,
                required_years=vacancy_skill.minimum_years,
            ))
        
        # Calculate statistics
        result.total_vacancy_skills = len(vacancy_skills)
        result.matched_total_skills = len(matched_ids)
        
        # Calculate required skills statistics
        required_skills = {
            sid for sid, skill in vacancy_skills.items() 
            if skill.is_required
        }
        result.total_required_skills = len(required_skills)
        result.matched_required_skills = len(matched_ids & required_skills)
        
        # Calculate percentages
        if result.total_vacancy_skills > 0:
            result.match_percentage = (
                result.matched_total_skills / result.total_vacancy_skills
            ) * 100
        
        # Sort results: required skills first, then by name
        result.matched_skills.sort(
            key=lambda x: (not x.is_required, x.skill_name)
        )
        result.missing_skills.sort(
            key=lambda x: (not x.is_required, x.skill_name)
        )
        
        return result

    @classmethod
    def get_skill_match(cls, vacancy, resume) -> Optional[dict]:
        """
        Get skill match for a single vacancy-resume pair.
        
        This is the main method for candidate view.
        
        Args:
            vacancy: Vacancy instance (prefetch vacancyskill_set__skill)
            resume: Resume instance (prefetch resume_skills__skill) or None
            
        Returns:
            Dictionary with skill match data or None if no vacancy skills
        """
        vacancy_skills = cls.get_vacancy_skills(vacancy)
        
        if not vacancy_skills:
            return None
        
        resume_skills = cls.get_resume_skills(resume)
        result = cls.calculate_match(vacancy_skills, resume_skills)
        
        return result.to_dict()

    @classmethod
    def get_skill_match_for_candidate(cls, vacancy, candidate) -> Optional[dict]:
        """
        Get skill match for a candidate's main resume.
        
        Fetches the candidate's main resume and calculates match.
        
        Args:
            vacancy: Vacancy instance
            candidate: Candidate instance
            
        Returns:
            Dictionary with skill match data or None
        """
        if candidate is None:
            return None
        
        # Get main resume with prefetched skills
        resume = candidate.resumes.filter(
            is_main=True
        ).prefetch_related(
            'resume_skills__skill'
        ).first()
        
        return cls.get_skill_match(vacancy, resume)

    @classmethod
    def bulk_get_skill_match(cls, vacancy, applications) -> dict:
        """
        Get skill matches for multiple applications efficiently.
        
        This is optimized for recruiter views where we need to
        calculate matches for many candidates at once.
        
        The applications queryset should be prefetched with:
        - candidate__prefetched_main_resumes (to_attr list filtered to is_main=True)
        - candidate__prefetched_main_resumes__resume_skills__skill

        Also supports legacy prefetch cache access via candidate._prefetched_objects_cache['resumes'].
        
        Args:
            vacancy: Vacancy instance with prefetched skills
            applications: QuerySet of JobApplication instances
            
        Returns:
            Dictionary mapping application_id to skill match data
        """
        # Get vacancy skills once
        vacancy_skills = cls.get_vacancy_skills(vacancy)
        
        if not vacancy_skills:
            return {}
        
        results = {}
        
        for application in applications:
            # Get candidate's main resume from prefetched data
            candidate = application.candidate
            main_resume = None

            # Preferred path: explicit to_attr prefetch for main resumes.
            prefetched_main_resumes = getattr(candidate, 'prefetched_main_resumes', None)
            if prefetched_main_resumes:
                main_resume = prefetched_main_resumes[0]
            
            # Legacy path: access prefetched resumes relation cache.
            if main_resume is None and hasattr(candidate, '_prefetched_objects_cache'):
                resumes = getattr(candidate, '_prefetched_objects_cache', {}).get('resumes', [])
                for resume in resumes:
                    if resume.is_main:
                        main_resume = resume
                        break
            
            # Fallback if not prefetched.
            if main_resume is None:
                main_resume = candidate.resumes.filter(is_main=True).first()
            
            # Calculate match
            resume_skills = cls.get_resume_skills(main_resume)
            result = cls.calculate_match(vacancy_skills, resume_skills)
            
            results[str(application.id)] = result.to_dict()
        
        return results
