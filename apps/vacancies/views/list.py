import logging
from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django.db.models import Q, Count, Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from ..serializers import VacancySerializer
from ..models import FavouriteVacancy, Vacancy, VacancyLanguage, VacancySkill
from ..filters import VacancyFilter
from apps.authentication.models import Recruiter, Candidate
from apps.applications.models.choices import ApplicationStatus
from core.responses import APIResponse
from utils.view_mixins import RecruiterMixin
from utils.language import get_request_language
from apps.matching.services.matching import VacancyMatcher
from apps.profiles.models import CompanyProfile
from django.utils.translation import gettext as _
from .mixins import _with_application_counts
from .choices import VacancyStatusChoicesView

logger = logging.getLogger(__name__)


@extend_schema_view(
    get=extend_schema(
        summary="List vacancies (candidate-facing)",
        description="List active vacancies with filtering, search, and sorting. "
                    "For authenticated candidates, excludes already-applied vacancies and "
                    "returns similarity-matched ordering based on the candidate's main resume embedding. "
                    "Supports extensive filtering via query parameters.",
    ),
)
class VacancyListView(generics.ListAPIView):

    def get_candidate(self):
        target = getattr(self.request, "_request", self.request)
        cached = getattr(target, "_candidate_cache", None)
        if cached is not None:
            return cached
        if getattr(target, "_candidate_resolved", False):
            return None
        try:
            candidate = Candidate.objects.get(email=self.request.user.email)
            setattr(target, "_candidate_cache", candidate)
            setattr(target, "_candidate_resolved", True)
            return candidate
        except Candidate.DoesNotExist:
            setattr(target, "_candidate_resolved", True)
            return None

    def get_candidate_resume(self, candidate):
        target = getattr(self.request, "_request", self.request)
        if hasattr(target, "_cached_resume"):
            return target._cached_resume

        from apps.resumes.models import Resume

        resume = Resume.objects.filter(
            candidate=candidate,
            is_main=True,
            is_embedded=True,
            embedding__isnull=False
        ).order_by("-created_at").first()

        if not resume:
            resume = Resume.objects.filter(
                candidate=candidate,
                is_embedded=True,
                embedding__isnull=False
            ).order_by("-created_at").first()

        if not resume:
            logger.info(
                "No embedded resume found for candidate %s — vacancy matching skipped.",
                candidate.id,
            )

        setattr(target, "_cached_resume", resume)
        return resume

    def get_queryset(self):
        queryset = _with_application_counts(
            Vacancy.objects.filter(is_active=True, is_demo=False)
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

        candidate = None
        if self.request.user.is_authenticated and getattr(
                self.request.user, "is_candidate", False
        ):
            candidate = self.get_candidate()
            if candidate:
                queryset = queryset.exclude(
                    applications__candidate=candidate
                )

                resume = self.get_candidate_resume(candidate)

                if resume:
                    self.request._candidate_resume = resume

                queryset = queryset.order_by("-created_at", "id")
            else:
                queryset = queryset.order_by("-created_at", "id")
        else:
            queryset = queryset.order_by("-created_at", "id")

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        language = get_request_language()

        if hasattr(self.request, '_candidate_resume') and self.request._candidate_resume:
            try:
                from django.db.models import Case, When, IntegerField, Value

                resume = self.request._candidate_resume

                top_k = 200
                min_similarity = 0.1

                matching_vacancies = VacancyMatcher.find_matching_vacancies(
                    resume=resume,
                    top_k=top_k,
                    min_similarity=min_similarity
                )

                if matching_vacancies:
                    similarity_map = {
                        str(v.id): v.similarity_score
                        for v in matching_vacancies
                    }

                    matched_ids = list(similarity_map.keys())

                    match_rank_cases = Case(
                        *[When(id=vid, then=Value(i)) for i, vid in enumerate(matched_ids)],
                        default=Value(len(matched_ids)),
                        output_field=IntegerField(),
                    )

                    combined_qs = queryset.annotate(
                        match_rank=match_rank_cases
                    ).order_by('match_rank', '-created_at', 'id')

                    page = self.paginate_queryset(combined_qs)
                    if page is not None:
                        for v in page:
                            v.similarity_score = similarity_map.get(str(v.id))
                        serializer = self.get_serializer(page, many=True)
                        localized_data = [
                            VacancyStatusChoicesView.add_labels_to_vacancy_data(item, language)
                            for item in serializer.data
                        ]
                        return self.get_paginated_response(localized_data)

                    for v in combined_qs:
                        v.similarity_score = similarity_map.get(str(v.id))
                    serializer = self.get_serializer(combined_qs, many=True)
                    localized_data = [
                        VacancyStatusChoicesView.add_labels_to_vacancy_data(item, language)
                        for item in serializer.data
                    ]
                    return APIResponse.success(
                        data=localized_data,
                        message=_("Vacancies matched and listed successfully."),
                    )

            except Exception as e:
                logger.warning(f"Resume matching failed: {e}. Falling back to default ordering.")

        page = self.paginate_queryset(queryset)
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
            message=_("Vacancies listed successfully"),
        )

    def get_filterset(self, *args, **kwargs):
        filterset = super().get_filterset(*args, **kwargs)
        if filterset:
            filterset.request = self.request
        return filterset

    def get_serializer_context(self):
        context = super().get_serializer_context()

        if self.request.user.is_authenticated and getattr(
            self.request.user, "is_candidate", False
        ):
            candidate = self.get_candidate()
            context["candidate"] = candidate

            if candidate:
                context["candidate_applications"] = {}
                context["favourite_vacancy_ids"] = set(
                    FavouriteVacancy.objects.filter(candidate=candidate).values_list(
                        "vacancy_id", flat=True
                    )
                )

                target = getattr(self.request, "_request", self.request)
                if hasattr(target, "_cached_context_resume"):
                    context["candidate_resume"] = target._cached_context_resume
                else:
                    from apps.resumes.models import Resume
                    resume = Resume.objects.filter(
                        candidate=candidate,
                        is_main=True
                    ).prefetch_related(
                        'resume_skills__skill'
                    ).order_by("-created_at").first()
                    target._cached_context_resume = resume
                    context["candidate_resume"] = resume

            if candidate:
                from apps.student_analytics.models import VacancySkillRoadmap
                roadmaps = VacancySkillRoadmap.objects.filter(
                    application__candidate=candidate,
                ).select_related("application").prefetch_related("items__skill")
                context["roadmaps_by_vacancy"] = {r.application.vacancy_id: r for r in roadmaps}

        return context

    queryset = Vacancy.objects.none()
    serializer_class = VacancySerializer
    permission_classes = []

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
    ]
    filterset_class = VacancyFilter
    search_fields = ["title", "company__name"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]


class RecruiterVacancyListView(RecruiterMixin, generics.ListAPIView):

    serializer_class = VacancySerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = VacancyFilter
    search_fields = [
        "title",
        "company__name",
        "employment_type",
        "employment_format",
    ]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["show_inactive_skills"] = True
        return context

    def list(self, request, *args, **kwargs):
        if not request.user.is_recruiter:
            raise PermissionDenied(_("Only recruiters can access this view"))
        try:
            recruiter = self.get_recruiter()
        except Recruiter.DoesNotExist:
            recruiter = None

        if not recruiter or not recruiter.company or not recruiter.company.is_active:
            from apps.vacancies.services.demo_data import get_demo_vacancies
            from apps.skills.localization import user_preferred_language
            language = user_preferred_language(request.user)
            vacancies = get_demo_vacancies(language)
            return Response({
                "count": len(vacancies),
                "next": None,
                "previous": None,
                "limit": 20,
                "offset": 0,
                "results": vacancies,
            })
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user

        if not user.is_recruiter:
            raise PermissionDenied(_("Only recruiters can access this view"))

        try:
            recruiter = self.get_recruiter()

            return (
                Vacancy.objects.filter(created_by=recruiter, is_active=True, is_demo=False)
                .annotate(
                    applications_count_value=Count("applications"),
                    applied_applications_count=Count(
                        "applications",
                        filter=Q(applications__status=ApplicationStatus.APPLIED)
                               & ~Q(applications__status=ApplicationStatus.WITHDRAWN),
                    ),
                )
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
                .order_by("-created_at")
            )
        except Recruiter.DoesNotExist:
            return Vacancy.objects.none()


class InactiveVacancyListView(RecruiterMixin, generics.ListAPIView):

    serializer_class = VacancySerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["show_inactive_skills"] = True
        return context

    def get_queryset(self):
        user = self.request.user

        if not user.is_recruiter:
            return Vacancy.objects.none()

        try:
            recruiter = self.get_recruiter()
            return (
                Vacancy.objects.filter(created_by=recruiter, is_active=False, is_demo=False)
                .annotate(
                    applications_count_value=Count("applications"),
                    applied_applications_count=Count(
                        "applications",
                        filter=Q(applications__status=ApplicationStatus.APPLIED)
                               & ~Q(applications__status=ApplicationStatus.WITHDRAWN),
                    ),
                )
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
                .order_by("-created_at")
            )
        except Recruiter.DoesNotExist:
            return Vacancy.objects.none()


vacancy_list_view = VacancyListView.as_view()
recruiter_vacancy_list_view = RecruiterVacancyListView.as_view()
inactive_vacancy_list_view = InactiveVacancyListView.as_view()
