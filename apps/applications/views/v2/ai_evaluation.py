"""
v2 AI Evaluation view.

Provides GET /api/v2/applications/{application_id}/ai-evaluation/
for recruiters to retrieve the full AI evaluation for a candidate.

The result JSON contains tri-language text fields (uz, ru, en).
The response localizes text fields to the viewer's language.
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.views import APIView

from core.responses import APIResponse

from apps.applications.models import JobApplication, ApplicationAIEvaluation, EvaluationStatus
from utils.language import get_request_language

logger = logging.getLogger(__name__)


def _localize_result(result: dict | None, language: str) -> dict | None:
    """
    Localize tri-language text fields in the AI evaluation result.

    Text fields stored as dicts with uz/ru/en keys are resolved to the
    requested language, falling back to uz then empty string.
    """
    if not result:
        return None

    localized = dict(result)

    text_fields = ["summary", "experience_summary", "education_summary", "activity_summary"]
    list_fields = ["red_flags", "strengths"]

    for field in text_fields:
        value = result.get(field)
        if isinstance(value, dict):
            localized[field] = (
                value.get(language) or value.get("uz") or value.get("en") or ""
            )

    for field in list_fields:
        value = result.get(field)
        if isinstance(value, dict):
            localized[field] = (
                value.get(language) or value.get("uz") or value.get("en") or []
            )

    # Localize nested match_breakdown details
    match_breakdown = result.get("match_breakdown")
    if isinstance(match_breakdown, dict):
        localized_breakdown = {}
        for key, item in match_breakdown.items():
            if isinstance(item, dict):
                loc_item = dict(item)
                details = item.get("details")
                if isinstance(details, list):
                    loc_details = []
                    for d in details:
                        if isinstance(d, dict):
                            loc_details.append(
                                d.get(language) or d.get("uz") or d.get("en") or ""
                            )
                        else:
                            loc_details.append(str(d) if d is not None else "")
                    loc_item["details"] = loc_details
                localized_breakdown[key] = loc_item
            else:
                localized_breakdown[key] = item
        localized["match_breakdown"] = localized_breakdown

    return localized


class ApplicationAIEvaluationView(APIView):
    """
    Retrieve the AI evaluation for a specific job application.

    Only accessible by a recruiter who belongs to the same company
    as the vacancy the application is for.

    Text fields (summary, experience_summary, red_flags, strengths) are
    localized to the viewer's language (Accept-Language header).

    GET /api/v2/applications/{application_id}/ai-evaluation/
    """

    def get(self, request, application_id):
        # Must be authenticated recruiter
        user = request.user
        if not user.is_authenticated or not getattr(user, 'is_recruiter', False):
            raise PermissionDenied("Only recruiters can access AI evaluations.")

        try:
            recruiter = user.recruiter
        except AttributeError:
            raise PermissionDenied("Recruiter profile not found.")

        # Demo applications have no real DB row - serve the hardcoded result
        # directly, but only to recruiters whose own company is unapproved
        # (the same is_active gate used for the demo kanban/candidates list).
        # Otherwise a real company guessing a fake demo id would get served
        # someone else's "AI evaluation" for an application that isn't theirs.
        if recruiter.company_id and not recruiter.company.is_active:
            from apps.vacancies.services.demo_data import get_demo_ai_evaluation

            demo_result = get_demo_ai_evaluation(application_id)
            if demo_result is not None:
                viewer_language = get_request_language()
                data = {
                    "application_id": str(application_id),
                    "status": EvaluationStatus.COMPLETED,
                    "overall_score": demo_result["overall_score"],
                    "detected_language": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "thinking_tokens": None,
                    "evaluated_at": None,
                    "error_message": None,
                    "result": _localize_result(demo_result, viewer_language),
                }
                return APIResponse.success(data=data)

        # Fetch application and verify recruiter's company owns the vacancy
        application = get_object_or_404(
            JobApplication.objects.select_related(
                "vacancy",
                "vacancy__company",
                "candidate",
            ),
            id=application_id,
        )

        # Permission check: recruiter must belong to vacancy's company
        if str(application.vacancy.company_id) != str(recruiter.company_id):
            raise PermissionDenied(
                "You do not have permission to view this application's evaluation."
            )

        # Fetch evaluation record
        try:
            evaluation = ApplicationAIEvaluation.objects.get(application=application)
        except ApplicationAIEvaluation.DoesNotExist:
            raise NotFound("AI evaluation not found for this application.")

        # Localize result to the viewer's language
        viewer_language = get_request_language()
        localized_result = _localize_result(evaluation.result, viewer_language)

        data = {
            "application_id": str(application_id),
            "status": evaluation.status,
            "overall_score": evaluation.overall_score,
            "detected_language": evaluation.detected_language,
            "input_tokens": evaluation.input_tokens,
            "output_tokens": evaluation.output_tokens,
            "thinking_tokens": evaluation.thinking_tokens,
            "evaluated_at": evaluation.evaluated_at,
            "error_message": evaluation.error_message if evaluation.status == EvaluationStatus.FAILED else None,
            "result": localized_result,
        }

        return APIResponse.success(data=data)


ai_evaluation_view = ApplicationAIEvaluationView.as_view()
