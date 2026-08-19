
import logging
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from apps.resumes.models import Resume
from apps.vacancies.models import Vacancy
from apps.vacancies.serializers import VacancySerializer
from apps.resumes.serializers import ResumeSerializer
from core.responses import APIResponse
from utils import IsRecruiterPermission
from .services.matching import VacancyMatcher
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def _get_match_quality(score):
    """Convert similarity score to human-readable quality rating."""
    if score >= 0.8:
        return "Excellent"
    elif score >= 0.7:
        return "Very Good"
    elif score >= 0.6:
        return "Good"
    elif score >= 0.5:
        return "Fair"
    else:
        return "Poor"


class MatchResumeToVacanciesView(APIView):
    """
    Match a specific resume to all available vacancies.

    Returns the top matching vacancies ranked by similarity score.

    **Query Parameters**:
    - top_k (int, optional): Number of results to return (default: 20, max: 50)
    - min_similarity (float, optional): Minimum similarity score 0-1 (default: 0.3)

    **Returns**:
    {
        "resume_id": "uuid",
        "resume_title": "Senior Developer Resume",
        "matches_found": 15,
        "matches": [
            {
                "vacancy": { ...vacancy data... },
                "similarity_score": 0.87,
                "match_percentage": 87,
                "match_quality": "Excellent"
            }
        ]
    }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, resume_id):
        # Safely parse query parameters with input validation
        try:
            top_k = min(int(request.query_params.get("top_k", 20)), 50)
        except (ValueError, TypeError):
            return APIResponse.validation_error(
                message=_("Invalid top_k parameter"),
                field_errors={"top_k": ["Must be a valid integer."]},
            )

        try:
            min_similarity = float(request.query_params.get("min_similarity", 0.3))
        except (ValueError, TypeError):
            return APIResponse.validation_error(
                message=_("Invalid min_similarity parameter"),
                field_errors={"min_similarity": ["Must be a valid number."]},
            )

        # Validate min_similarity range
        if not 0 <= min_similarity <= 1:
            return APIResponse.validation_error(
                message=_("min_similarity must be between 0 and 1"),
                field_errors={"min_similarity": ["Must be between 0 and 1."]},
            )

        # Get the resume
        resume = get_object_or_404(Resume, id=resume_id)

        # ponytail: owner-or-recruiter check — candidates can only match their own resume
        user = request.user
        is_owner = getattr(resume.candidate, "id", None) == getattr(user, "id", None)
        if not is_owner and not getattr(user, "is_recruiter", False):
            return APIResponse.not_found(message=_("Resume not found."))

        # Check if resume has embedding
        if not resume.is_embedded or resume.embedding is None:
            return APIResponse.bad_request(
                message=_("Resume embedding not generated yet"),
                details=_("Please wait a moment and try again. Embeddings are being processed."),
            )

        # Perform matching
        try:
            matching_vacancies = VacancyMatcher.find_matching_vacancies(
                resume=resume, top_k=top_k, min_similarity=min_similarity
            )
        except Exception as e:
            logger.error(f"Matching failed for resume {resume_id}: {e}", exc_info=True)
            return APIResponse.server_error(
                message=_("Matching failed"),
                details=_("An error occurred while processing the match request."),
            )

        # Serialize results
        matches = []
        for vacancy in matching_vacancies:
            vacancy_data = VacancySerializer(vacancy).data

            match_info = {
                "vacancy": vacancy_data,
                "similarity_score": round(vacancy.similarity_score, 3),
                "match_percentage": round(vacancy.similarity_score * 100, 1),
                "match_quality": _get_match_quality(vacancy.similarity_score),
            }
            matches.append(match_info)

        return APIResponse.success(
            data={
                "resume_id": str(resume.id),
                "resume_title": resume.title,
                "matches_found": len(matches),
                "matches": matches,
            },
            message=_("Matching completed successfully"),
        )

class MatchVacancyToResumesView(APIView):
    """
    Match a specific vacancy to all available resumes.

    Returns the top matching resumes ranked by similarity score.

    **Query Parameters**:
    - top_k (int, optional): Number of results to return (default: 20, max: 50)
    - min_similarity (float, optional): Minimum similarity score 0-1 (default: 0.5)

    **Returns**:
    {
        "vacancy_id": "uuid",
        "vacancy_title": "Senior Backend Developer",
        "matches_found": 12,
        "matches": [
            {
                "resume": { ...resume data... },
                "similarity_score": 0.85,
                "match_percentage": 85,
                "match_quality": "Excellent"
            }
        ]
    }
    """

    permission_classes = [IsRecruiterPermission]

    def get(self, request, vacancy_id):
        # Safely parse query parameters with input validation
        try:
            top_k = min(int(request.query_params.get("top_k", 20)), 50)
        except (ValueError, TypeError):
            return APIResponse.validation_error(
                message=_("Invalid top_k parameter"),
                field_errors={"top_k": ["Must be a valid integer."]},
            )

        try:
            min_similarity = float(request.query_params.get("min_similarity", 0.3))
        except (ValueError, TypeError):
            return APIResponse.validation_error(
                message=_("Invalid min_similarity parameter"),
                field_errors={"min_similarity": ["Must be a valid number."]},
            )

        # Validate min_similarity range
        if not 0 <= min_similarity <= 1:
            return APIResponse.validation_error(
                message=_("min_similarity must be between 0 and 1"),
                field_errors={"min_similarity": ["Must be between 0 and 1."]},
            )

        # Get the vacancy with select_related to avoid N+1 on company access
        vacancy = get_object_or_404(
            Vacancy.objects.select_related("company"), id=vacancy_id
        )

        # Check if vacancy has embedding
        if not vacancy.is_embedded or vacancy.embedding is None:
            return APIResponse.bad_request(
                message=_("Vacancy embedding not generated yet"),
                details=_("Please wait a moment and try again. Embeddings are being processed."),
            )

        # Perform matching
        try:
            matching_resumes = VacancyMatcher.find_matching_resumes(
                vacancy=vacancy, top_k=top_k, min_similarity=min_similarity
            )
        except Exception as e:
            logger.error(f"Matching failed for vacancy {vacancy_id}: {e}", exc_info=True)
            return APIResponse.server_error(
                message=_("Matching failed"),
                details=_("An error occurred while processing the match request."),
            )

        # Serialize results
        matches = []
        for resume in matching_resumes:
            resume_data = ResumeSerializer(resume, context={"request": request}).data

            match_info = {
                "resume": resume_data,
                "similarity_score": round(resume.similarity_score, 3),
                "match_percentage": round(resume.similarity_score * 100, 1),
                "match_quality": _get_match_quality(resume.similarity_score),
            }
            matches.append(match_info)

        return APIResponse.success(
            data={
                "vacancy_id": str(vacancy.id),
                "vacancy_title": vacancy.title,
                "company_name": vacancy.company.name,
                "matches_found": len(matches),
                "matches": matches,
            },
            message=_("Matching completed successfully"),
        )

# Export view instances
match_resume_to_vacancies = MatchResumeToVacanciesView.as_view()
match_vacancy_to_resumes = MatchVacancyToResumesView.as_view()
