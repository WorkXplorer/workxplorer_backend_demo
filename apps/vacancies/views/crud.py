import logging
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from utils import IsRecruiterPermission
from django.http import Http404
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django_rq import enqueue
from ..serializers import VacancySerializer
from ..models import Vacancy, VacancyLanguage
from apps.authentication.models import Recruiter
from utils.company_permission import IsCompanyApproved
from apps.subscriptions.permissions import (
    CanCreateVacancy,
    CanSetVacancyExpire,
    get_cached_company,
    get_cached_subscription,
    get_cached_features,
)
from apps.subscriptions.services import SubscriptionService
from apps.matching.services.embedding_tasks import generate_vacancy_embedding_task
from core.responses import APIResponse
from django.utils.translation import gettext as _
from django.db.models import Prefetch

logger = logging.getLogger(__name__)


class CreateVacancyView(generics.CreateAPIView):

    queryset = Vacancy.objects.all()
    serializer_class = VacancySerializer
    permission_classes = [IsAuthenticated, IsRecruiterPermission, IsCompanyApproved, CanCreateVacancy, CanSetVacancyExpire]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["show_inactive_skills"] = True
        return context

    @extend_schema(
        request=VacancySerializer,
        responses={
            201: OpenApiResponse(
                response=VacancySerializer,
                description="Vacancy created successfully",
            ),
            400: OpenApiResponse(description="Bad request - validation errors"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden - subscription limit exceeded"),
        },
    )

    def get_recruiter_and_company(self):
        user = self.request.user

        if not user.is_recruiter:
            raise Http404("Only recruiters can create vacancies")

        from apps.subscriptions.permissions import get_cached_recruiter, set_cached_recruiter
        recruiter = get_cached_recruiter(self.request)
        if recruiter is None:
            try:
                recruiter = Recruiter.objects.select_related("company").get(
                    email=user.email
                )
                set_cached_recruiter(self.request, recruiter)
            except Recruiter.DoesNotExist:
                raise Http404("Recruiter not found")

        if not recruiter.company:
            raise Http404(
                "Recruiter must be associated with a company to create vacancies"
            )

        if not recruiter.company.is_active:
            raise PermissionDenied(
                _("Your company account is not active. Please contact support.")
            )

        return recruiter, recruiter.company

    def perform_create(self, serializer):
        recruiter, company = self.get_recruiter_and_company()
        vacancy = serializer.save(created_by=recruiter, company=company)

        enqueue(generate_vacancy_embedding_task, vacancy.id)

    def create(self, request, *args, **kwargs):
        try:
            self.get_recruiter_and_company()
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)

            return APIResponse.created(
                data=serializer.data,
                message=_("Vacancy created successfully. Embedding generation started in background."),
            )

        except Http404 as e:
            return APIResponse.forbidden(
                message=str(e),
            )
        except PermissionDenied as e:
            return APIResponse.forbidden(
                message=str(e),
            )
        except serializers.ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error creating vacancy: {e}", exc_info=True)
            return APIResponse.server_error(
                message=_("Failed to create vacancy"),
                details=_("An unexpected error occurred while creating your vacancy."),
            )


class UpdateVacancyView(generics.UpdateAPIView):

    queryset = Vacancy.objects.all()
    serializer_class = VacancySerializer
    permission_classes = [IsAuthenticated, IsRecruiterPermission, CanSetVacancyExpire]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["show_inactive_skills"] = True
        return context

    @extend_schema(
        request=VacancySerializer,
        responses={
            200: OpenApiResponse(
                response=VacancySerializer,
                description="Vacancy updated successfully",
            ),
            400: OpenApiResponse(description="Bad request - validation errors"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden - not authorized to update this vacancy"),
            404: OpenApiResponse(description="Vacancy not found"),
        },
    )

    def get_object(self):
        vacancy_id = self.kwargs["id"]
        try:
            vacancy = Vacancy.objects.select_related(
                "created_by", "company", "domain"
            ).prefetch_related(
                "vacancyskill_set__skill",
                Prefetch(
                    "vacancy_languages",
                    queryset=VacancyLanguage.objects.select_related("language"),
                ),
                "company__companyprofile",
            ).get(id=vacancy_id)
            if vacancy.created_by_id != self.request.user.pk:
                raise Http404("You do not have permission to update this vacancy")
            return vacancy
        except Vacancy.DoesNotExist:
            raise Http404("Vacancy not found")

    def update(self, request, *args, **kwargs):
        from django.db.models import Prefetch
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        vacancy = serializer.save()
        vacancy.expire_vacancy()

        vacancy = Vacancy.objects.select_related(
            "company", "created_by", "domain"
        ).prefetch_related(
            "vacancyskill_set__skill",
            Prefetch(
                "vacancy_languages",
                queryset=VacancyLanguage.objects.select_related("language"),
            ),
            "company__companyprofile",
        ).get(id=vacancy.id)
        response_serializer = self.get_serializer(vacancy)

        return APIResponse.success(
            data=response_serializer.data,
            message=_("Vacancy updated successfully"),
        )


class ArchiveVacancyView(generics.UpdateAPIView):

    queryset = Vacancy.objects.all()
    serializer_class = VacancySerializer
    permission_classes = [IsAuthenticated, IsRecruiterPermission]

    def get_object(self):
        vacancy_id = self.kwargs["id"]
        company = get_cached_company(self.request)
        if not company:
            raise Http404("Recruiter is not associated with a company")
        try:
            vacancy = Vacancy.objects.select_related("created_by").get(
                id=vacancy_id, company=company
            )
            if vacancy.created_by_id != self.request.user.pk:
                raise Http404("You do not have permission to archive this vacancy")
            return vacancy
        except Vacancy.DoesNotExist:
            raise Http404("Vacancy not found")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        allowed_fields = {"is_active"}
        received_fields = set(request.data.keys())

        if not received_fields:
            return APIResponse.validation_error(
                message=_("No fields provided"),
            )

        extra = received_fields - allowed_fields
        if extra:
            return APIResponse.validation_error(
                message=_("Only `is_active` may be updated"),
                details={"invalid_fields": list(extra)},
            )

        if "is_active" not in request.data:
            return APIResponse.validation_error(
                message=_("`is_active` is required"),
                field_errors={"is_active": ["This field is required."]},
            )

        value = request.data.get("is_active")

        if isinstance(value, str):
            val_lower = value.strip().lower()
            if val_lower in ("true", "1", "yes", "y"):
                new_value = True
            elif val_lower in ("false", "0", "no", "n"):
                new_value = False
            else:
                return APIResponse.validation_error(
                    message=_("Invalid boolean value for `is_active`"),
                    field_errors={"is_active": ["Must be a boolean value."]},
                )
        else:
            new_value = bool(value)

        # Check subscription limit when un-archiving (is_active going False → True)
        if new_value and not instance.is_active:
            company = get_cached_company(request)
            if not company:
                return APIResponse.bad_request(
                    message=_("Recruiter is not associated with a company"),
                )
            result = SubscriptionService.check_vacancy_limit(
                company,
                subscription=get_cached_subscription(request),
                features=get_cached_features(request),
            )
            if not result["allowed"]:
                return APIResponse.bad_request(
                    message=result.get("error", ""),
                )

        instance.is_active = new_value
        instance.save(update_fields=["is_active"])

        return APIResponse.success(
            data={
                "vacancy_id": str(instance.id),
                "is_active": instance.is_active,
            },
            message=_("Vacancy `is_active` updated successfully"),
        )


class DeleteVacancyView(generics.DestroyAPIView):

    queryset = Vacancy.objects.all()
    serializer_class = VacancySerializer
    permission_classes = [IsAuthenticated, IsRecruiterPermission]

    def get_object(self):
        vacancy_id = self.kwargs["id"]
        try:
            vacancy = Vacancy.objects.select_related("created_by").get(id=vacancy_id)
            if vacancy.created_by_id != self.request.user.pk:
                raise Http404("You do not have permission to delete this vacancy")
            return vacancy
        except Vacancy.DoesNotExist:
            raise Http404("Vacancy not found")

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        vacancy_id = instance.id
        vacancy_title = instance.title
        self.perform_destroy(instance)
        return APIResponse.success(
            data={"vacancy_id": str(vacancy_id), "title": vacancy_title},
            message=_("Vacancy deleted successfully"),
        )


create_vacancy_view = CreateVacancyView.as_view()
update_vacancy_view = UpdateVacancyView.as_view()
archive_vacancy_view = ArchiveVacancyView.as_view()
delete_vacancy_view = DeleteVacancyView.as_view()
