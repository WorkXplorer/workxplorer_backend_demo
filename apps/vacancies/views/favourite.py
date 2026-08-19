from django.db import IntegrityError, transaction
from rest_framework import generics, serializers
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample, inline_serializer
from ..serializers import VacancySerializer
from ..models import FavouriteVacancy, Vacancy, VacancyLanguage, VacancySkill
from core.responses import APIResponse
from utils.candidate_permission import IsCandidatePermission
from utils.language import get_request_language
from apps.profiles.models import CompanyProfile
from django.utils.translation import gettext as _
from django.db.models import Prefetch
from .mixins import _resolve_candidate_from_request, _with_application_counts
from .choices import VacancyStatusChoicesView


@extend_schema_view(
    get=extend_schema(
        summary="List favourite vacancies",
        description="Get the candidate's favourite/saved vacancies. Returns full vacancy data with all nested relations.",
        responses={
            200: OpenApiResponse(
                response=VacancySerializer(many=True),
                description="Paginated list of favourite vacancies",
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
        },
    ),
)
class CandidateFavouriteVacancyListView(generics.ListAPIView):

    serializer_class = VacancySerializer
    permission_classes = [IsCandidatePermission]

    def get_candidate(self):
        return _resolve_candidate_from_request(self.request)

    def get_queryset(self):
        candidate = self.get_candidate()
        if candidate is None:
            return Vacancy.objects.none()

        return _with_application_counts(
            Vacancy.objects.filter(favourite_vacancy_entries__candidate=candidate, is_demo=False)
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
            .order_by("-favourite_vacancy_entries__created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        candidate = self.get_candidate()

        if candidate is None:
            context["candidate"] = None
            context["candidate_applications"] = {}
            context["candidate_resume"] = None
            context["favourite_vacancy_ids"] = set()
            return context

        from apps.applications.models import JobApplication
        from apps.resumes.models import Resume

        candidate_applications = {
            app.vacancy_id: app
            for app in JobApplication.objects.filter(
                candidate=candidate
            ).only("id", "vacancy_id", "status", "applied_at")
        }

        candidate_resume = Resume.objects.filter(
            candidate=candidate,
            is_main=True,
        ).prefetch_related("resume_skills__skill").first()

        context["candidate"] = candidate
        context["candidate_applications"] = candidate_applications
        context["candidate_resume"] = candidate_resume
        context["favourite_vacancy_ids"] = set(
            FavouriteVacancy.objects.filter(candidate=candidate).values_list(
                "vacancy_id", flat=True
            )
        )

        from apps.student_analytics.models import VacancySkillRoadmap
        roadmaps = VacancySkillRoadmap.objects.filter(
            application__candidate=candidate,
        ).select_related("application").prefetch_related("items__skill")
        context["roadmaps_by_vacancy"] = {r.application.vacancy_id: r for r in roadmaps}

        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        language = get_request_language()

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            localized_data = [
                VacancyStatusChoicesView.add_labels_to_vacancy_data(item, language)
                for item in serializer.data
            ]
            return self.get_paginated_response(localized_data)

        serializer = self.get_serializer(queryset, many=True)
        localized_data = [
            VacancyStatusChoicesView.add_labels_to_vacancy_data(item, language)
            for item in serializer.data
        ]
        return APIResponse.success(
            data=localized_data,
            message=_("Favourite vacancies listed successfully"),
        )


class ToggleFavouriteVacancyView(APIView):

    permission_classes = [IsCandidatePermission]

    @extend_schema(
        summary="Toggle favourite vacancy",
        description="Add or remove a vacancy from the candidate's favourites list. "
                    "If the vacancy is already favourited, it is removed. Otherwise, it is added.",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "ToggleFavouriteResponse",
                    fields={
                        "vacancy_id": serializers.UUIDField(),
                        "is_favourite": serializers.BooleanField(),
                        "action": serializers.ChoiceField(choices=[("added", "Added"), ("removed", "Removed")]),
                    },
                ),
                description="Favourite status toggled successfully",
                examples=[
                    OpenApiExample(
                        "Added",
                        value={
                            "success": True,
                            "data": {"vacancy_id": "550e8400-e29b-41d4-a716-446655440000", "is_favourite": True, "action": "added"},
                            "message": "Vacancy added to favourites",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                    OpenApiExample(
                        "Removed",
                        value={
                            "success": True,
                            "data": {"vacancy_id": "550e8400-e29b-41d4-a716-446655440000", "is_favourite": False, "action": "removed"},
                            "message": "Vacancy removed from favourites",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                ],
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Vacancy not found"),
        }
    )
    def post(self, request, *args, **kwargs):
        candidate = _resolve_candidate_from_request(request)
        if candidate is None:
            return APIResponse.not_found(
                message=_("Candidate not found"),
                resource=_("Candidate"),
            )

        vacancy_id = kwargs.get("id")

        try:
            vacancy = Vacancy.objects.only("id").get(id=vacancy_id, is_demo=False)
        except Vacancy.DoesNotExist:
            return APIResponse.not_found(
                message=_("Vacancy not found"),
                resource=_("Vacancy"),
            )

        try:
            with transaction.atomic():
                favourite, created = FavouriteVacancy.objects.get_or_create(
                    candidate=candidate,
                    vacancy=vacancy,
                )
        except IntegrityError:
            favourite = FavouriteVacancy.objects.filter(
                candidate=candidate,
                vacancy=vacancy,
            ).first()
            created = favourite is not None

        if created:
            message = _("Vacancy added to favourites")
            action = "added"
            is_favourite = True
        else:
            favourite.delete()
            message = _("Vacancy removed from favourites")
            action = "removed"
            is_favourite = False

        return APIResponse.success(
            data={
                "vacancy_id": str(vacancy.id),
                "is_favourite": is_favourite,
                "action": action,
            },
            message=message,
        )


favourite_vacancy_list_view = CandidateFavouriteVacancyListView.as_view()
toggle_favourite_vacancy_view = ToggleFavouriteVacancyView.as_view()
