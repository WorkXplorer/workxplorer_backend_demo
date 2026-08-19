import logging
from rest_framework import generics
from django.db.models import Prefetch
from django.http import Http404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from ..serializers import VacancySerializer
from ..services import VacancyViewService
from ..models import FavouriteVacancy, Vacancy, VacancyLanguage, VacancySkill
from apps.authentication.models import Recruiter
from apps.subscriptions.permissions import get_cached_recruiter, set_cached_recruiter
from core.responses import APIResponse
from utils.language import get_request_language
from apps.profiles.models import CompanyProfile
from django.utils.translation import gettext as _
from .mixins import _resolve_candidate_from_request, _with_application_counts
from .choices import VacancyStatusChoicesView

logger = logging.getLogger(__name__)


class RetrieveVacancyView(generics.RetrieveAPIView):

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=VacancySerializer,
                description="Vacancy retrieved successfully",
            ),
            401: OpenApiResponse(description="Unauthorized"),
            404: OpenApiResponse(description="Vacancy not found"),
        }
    )

    def get_candidate(self):
        if not (
            self.request.user.is_authenticated
            and getattr(self.request.user, "is_candidate", False)
        ):
            return None

        return _resolve_candidate_from_request(self.request)

    def get_queryset(self):
        queryset = _with_application_counts(
            Vacancy.objects.filter(is_demo=False)
            .select_related("company", "created_by", "domain")
            .prefetch_related(
                Prefetch(
                    "vacancyskill_set",
                    queryset=VacancySkill.objects.select_related("skill"),
                ),
                Prefetch(
                    "vacancy_languages",
                    queryset=VacancyLanguage.objects.select_related("language"),
                ),
                Prefetch(
                    "company__companyprofile",
                    queryset=CompanyProfile.objects.only(
                        "id", "company_id", "address", "latitude", "longitude"
                    ),
                ),
            )
        )
        return queryset

    serializer_class = VacancySerializer
    permission_classes = []

    def retrieve(self, request, *args, **kwargs):
        from ..services.demo_data import DEMO_VACANCIES
        from utils.company_permission import IsCompanyApproved

        vacancy_id = str(self.kwargs["id"])
        if any(v["id"] == vacancy_id for v in DEMO_VACANCIES):
            return APIResponse.forbidden(
                message=str(IsCompanyApproved.message),
            )

        vacancy = self.get_object()

        show_inactive_skills = False
        if request.user.is_authenticated and request.user.is_recruiter:
            recruiter = get_cached_recruiter(request)
            if recruiter is None:
                try:
                    recruiter = Recruiter.objects.select_related("company").get(
                        email=request.user.email
                    )
                    set_cached_recruiter(request, recruiter)
                except Recruiter.DoesNotExist:
                    recruiter = None
            if recruiter and recruiter.company_id == vacancy.company_id:
                show_inactive_skills = True

        candidate = self.get_candidate()
        candidate_resume = None
        if candidate:
            from apps.resumes.models import Resume

            candidate_resume = Resume.objects.filter(
                candidate=candidate,
                is_main=True
            ).prefetch_related(
                "resume_skills__skill"
            ).first()

        favourite_vacancy_ids = set()
        if candidate:
            favourite_vacancy_ids = set(
                FavouriteVacancy.objects.filter(
                    candidate=candidate,
                    vacancy_id=vacancy.id,
                ).values_list("vacancy_id", flat=True)
            )

        serializer = self.get_serializer(
            vacancy,
            context={
                **self.get_serializer_context(),
                'candidate': candidate,
                'candidate_resume': candidate_resume,
                'favourite_vacancy_ids': favourite_vacancy_ids,
                'show_inactive_skills': show_inactive_skills,
            }
        )
        response_data = serializer.data

        language = get_request_language()
        response_data = VacancyStatusChoicesView.add_labels_to_vacancy_data(
            response_data, language
        )

        if candidate:
            vacancy_view, created = VacancyViewService.record_view(
                vacancy=vacancy, candidate=candidate
            )
            response_data["view_session_id"] = str(vacancy_view.id)

        return APIResponse.success(
            data=response_data,
            message=_("Vacancy retrieved successfully"),
        )

    def get_object(self):
        vacancy_id = self.kwargs["id"]
        try:
            obj = self.get_queryset().get(id=vacancy_id)
            self.check_object_permissions(self.request, obj)
            return obj
        except Vacancy.DoesNotExist:
            raise Http404("Vacancy not found")


retrieve_vacancy_view = RetrieveVacancyView.as_view()
