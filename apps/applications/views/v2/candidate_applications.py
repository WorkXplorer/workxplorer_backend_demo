"""
v2 kanban candidate-applications detail endpoint.

Same payload as the candidates-list detail endpoint (one shared service —
CandidateCompanyApplicationsService), exposed under the kanban URL space so
the board's card dropdown ("Отклики кандидата") has its own API.
"""

from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.applications.serializers.candidate_company import (
    CandidateCompanyApplicationsResponseSerializer,
)
from apps.applications.views.recruiter import CandidateCompanyApplicationsBaseView


@extend_schema(
    responses={
        200: OpenApiResponse(
            response=CandidateCompanyApplicationsResponseSerializer,
            description="All applications of the candidate to the company's vacancies, best AI match first",
        ),
        403: OpenApiResponse(description="Only recruiters can access this endpoint"),
        404: OpenApiResponse(description="Candidate has no applications in this company"),
    },
    description="Kanban detail: returns every application the candidate submitted to the "
                "recruiter's company, ordered by AI evaluation score (highest first, unscored last). "
                "Each entry contains the vacancy title, applied date (dd.mm.yyyy), AI score, "
                "localized status and the recruiter assigned to the vacancy (Vacancy.created_by). "
                "Visible only to recruiters/admins of the same company.",
)
class KanbanCandidateApplicationsView(CandidateCompanyApplicationsBaseView):
    """Kanban flavour of the candidate applications detail endpoint."""


kanban_candidate_applications_view = KanbanCandidateApplicationsView.as_view()
