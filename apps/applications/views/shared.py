from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.http import Http404
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from ..models import JobApplication
from ..serializers import JobApplicationDetailSerializer
from apps.authentication.models import Candidate, Recruiter
from apps.profiles.models import RecruiterProfile


@extend_schema_view(
    get=extend_schema(
        summary="Get application details",
        description="Get detailed information about a specific job application. "
                    "Candidates can only view their own applications. "
                    "Recruiters can only view applications to their company's vacancies. "
                    "Includes vacancy details, company info, skill matching, documents, "
                    "recruiter notes, and AI evaluation.",
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Application details",
            ),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Application not found or not accessible"),
        },
    ),
)
class ApplicationDetailView(generics.RetrieveAPIView):
    """
    Provides detailed view of a specific application.

    This serves both candidates (viewing their own applications)
    and recruiters (viewing applications to their vacancies).
    The permissions logic determines what level of detail to show.
    """

    serializer_class = JobApplicationDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """
        Retrieve the application with proper permission checking.
        Optimized to minimize database queries.
        """
        application_id = self.kwargs.get("application_id")
        user = self.request.user

        try:
            application = (
                JobApplication.objects.select_related(
                    "candidate",
                    "candidate__candidateprofile",
                    "vacancy",
                    "vacancy__company",
                    "vacancy__created_by",
                    "resume_used",
                    "last_updated_by",
                    "ai_evaluation",
                )
                .prefetch_related(
                    "documents",
                    "vacancy__vacancyskill_set__skill",
                    Prefetch(
                        "vacancy__created_by__recruiterprofile_set",
                        queryset=RecruiterProfile.objects.only("recruiter_id", "full_name"),
                        to_attr="prefetched_profiles",
                    ),
                    "resume_used__resume_skills__skill",
                )
                .get(id=application_id)
            )

            # Permission check: candidates can view their own applications,
            # recruiters can view applications to their company's vacancies
            if user.is_candidate:
                # Use the id directly since we already have the application's candidate loaded
                if str(application.candidate.email) != str(user.email):
                    raise Http404("You can only view your own applications")

            elif user.is_recruiter:
                recruiter_company_id = getattr(user, "company_id", None)
                if recruiter_company_id is None:
                    recruiter_company_id = Recruiter.objects.only("company_id").get(
                        pk=user.pk
                    ).company_id

                if application.vacancy.company_id != recruiter_company_id:
                    raise Http404(
                        "You can only view applications to your company's vacancies"
                    )

            else:
                raise Http404("Invalid user type")

            return application

        except (
                JobApplication.DoesNotExist,
                Candidate.DoesNotExist,
                Recruiter.DoesNotExist,
        ):
            raise Http404("Application not found")


application_detail_view = ApplicationDetailView.as_view()
