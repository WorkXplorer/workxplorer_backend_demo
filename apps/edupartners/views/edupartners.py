import uuid
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db.models import Q, Case, When, IntegerField, Value, CharField, F
from django.db.models.functions import Coalesce
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from apps.edupartners.models import EduPartner, EduPartnersType, Faculty, Subject
from apps.edupartners.serializers import (
    EduPartnerSerializer,
    EduPartnersTypeSerializer,
    FacultySerializer,
    SubjectSerializer,
    StudentSerializer,
)
from apps.edupartners.serializers.student_detail import StudentDetailSerializer
from apps.profiles.models import CandidateProfile
from utils.student_list_permission import IsEduPartnerService
from config.pagination import StudentListPagination
from datetime import timedelta
from uuid import UUID

class EduPartnerListAPIView(generics.ListAPIView):
    """
    Public API endpoint to list and search educational partners.
    - Supports searching by "q" across name, city, country, and type.
    - Supports filtering by type, country, and city.
    - Results ordered by relevance when searching
    Example:
        /api/edu-partners/?q=harvard
        /api/edu-partners/?city=Tashkent&type=University
        /api/edu-partners/?country=Uzbekistan
    """

    serializer_class = EduPartnerSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        # Database optimization - select related data in single query
        queryset = EduPartner.objects.filter(is_active=True).select_related(
            "edupartner_type"
        )

        # Global search (?q=) across all translated name fields
        q = self.request.query_params.get("q")
        if q:
            q_clean = q.strip()
            queryset = queryset.filter(
                Q(name_uz__icontains=q_clean)
                | Q(name_ru__icontains=q_clean)
                | Q(name_en__icontains=q_clean)
                | Q(city__icontains=q_clean)
                | Q(country__icontains=q_clean)
                | Q(edupartner_type__name__icontains=q_clean)
            ).distinct()

            # Order by relevance: exact matches first, then partial matches
            queryset = queryset.annotate(
                relevance_score=Case(
                    When(name_uz__iexact=q_clean, then=4),
                    When(name_ru__iexact=q_clean, then=4),
                    When(name_en__iexact=q_clean, then=4),
                    When(name_uz__istartswith=q_clean, then=3),
                    When(name_ru__istartswith=q_clean, then=3),
                    When(name_en__istartswith=q_clean, then=3),
                    When(name_uz__icontains=q_clean, then=2),
                    When(name_ru__icontains=q_clean, then=2),
                    When(name_en__icontains=q_clean, then=2),
                    default=1,
                    output_field=IntegerField(),
                )
            ).order_by("-relevance_score", "name")
        else:
            # Default ordering when no search
            queryset = queryset.order_by("created_at")

        # Filtering by specific fields
        edupartner_type = self.request.query_params.get("type")
        country = self.request.query_params.get("country")
        city = self.request.query_params.get("city")

        if edupartner_type:
            queryset = queryset.filter(edupartner_type__name__icontains=edupartner_type)

        if country:
            queryset = queryset.filter(country__icontains=country)

        if city:
            queryset = queryset.filter(city__icontains=city)

        return queryset


class EduPartnersTypeListAPIView(generics.ListAPIView):
    """
    Public API endpoint to list all educational partner types.
    Example: University, College, School, etc.
    """

    permission_classes = [AllowAny]
    queryset = EduPartnersType.objects.all().order_by("name")
    serializer_class = EduPartnersTypeSerializer
    http_method_names = ["get", "head", "options"]


class FacultyListAPIView(generics.ListAPIView):
    """
    Public API endpoint to list faculties.
    - Supports filtering by edupartner name or ID
    - Example: /api/faculties/?edupartner=harvard
    - Example: /api/faculties/?edupartner=<uuid>
    """

    serializer_class = FacultySerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        queryset = Faculty.objects.filter(is_active=True).select_related(
            "edupartner", "domain"
        )

        # Filter by edupartner (name in any language or ID)
        edupartner_param = self.request.query_params.get("edupartner")
        if edupartner_param:
            filters = Q(
                Q(edupartner__name_uz__icontains=edupartner_param)
                | Q(edupartner__name_ru__icontains=edupartner_param)
                | Q(edupartner__name_en__icontains=edupartner_param)
            )
            try:
                uuid.UUID(str(edupartner_param))
                filters |= Q(edupartner__id=edupartner_param)
            except (ValueError, AttributeError):
                pass
            queryset = queryset.filter(filters)

        return queryset.order_by("name")


class SubjectListAPIView(generics.ListAPIView):
    """
    Public API endpoint to list subjects.
    - Supports filtering by faculty ID
    - Example: /api/subjects/?faculty=<uuid>
    """

    serializer_class = SubjectSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        queryset = (
            Subject.objects.filter(is_active=True)
            .select_related("faculty")
            .prefetch_related("acquired_skills")
        )

        # Filter by faculty
        faculty_param = self.request.query_params.get("faculty")
        if faculty_param:
            queryset = queryset.filter(faculty__id=faculty_param)

        return queryset.order_by("name")


class StudentListAPIView(generics.ListAPIView):
    serializer_class = StudentSerializer
    permission_classes = [IsEduPartnerService]
    pagination_class = StudentListPagination
    VALID_STATUSES = {"active", "low_activity", "inactive"}


    def get_queryset(self):
        edupartner_id = self.request.query_params.get("edupartner_id")
        if not edupartner_id:
            raise ValidationError({"edupartner_id": _("This query parameter is required.")})

        try:
            UUID(str(edupartner_id))
        except (ValueError, TypeError):
            raise ValidationError({"edupartner_id": _("Must be a valid UUID.")})

        status_param = self.request.query_params.get("status")
        search = self.request.query_params.get("search")
        now = timezone.now()
        seven_days = now - timedelta(days=7)
        thirty_days = now - timedelta(days=30)

        queryset = (
            CandidateProfile.objects
            .select_related("candidate", "candidate__faculty", "candidate__edupartner")
            .annotate(
                activity_at=Coalesce("candidate__last_login", "candidate__date_joined"),
                status=Case(
                    When(activity_at__gte=seven_days, then=Value("active")),
                    When(activity_at__gte=thirty_days, then=Value("low_activity")),
                    default=Value("inactive"),
                    output_field=CharField(),
                ),
                edu_partner=F("candidate__edupartner__name"),
            )
        )

        queryset = queryset.filter(candidate__edupartner_id=edupartner_id)

        if search:
            search = search.strip()
            if search:
                queryset = queryset.filter(full_name__icontains=search)

        if status_param:
            statuses = [
                status.strip().lower()
                for status in status_param.split(",")
                if status.strip()
            ]
            valid_statuses = [
                status for status in statuses if status in self.VALID_STATUSES
            ]
            if valid_statuses:
                queryset = queryset.filter(status__in=valid_statuses)
            else:
                queryset = queryset.none()

        return queryset.order_by("-activity_at", "-created_at")


class StudentDetailAPIView(generics.RetrieveAPIView):
    serializer_class = StudentDetailSerializer
    permission_classes = [IsEduPartnerService]
    CACHE_TTL = 60 * 5

    def get_object(self):
        edupartner_id = self.request.query_params.get("edupartner_id")
        if not edupartner_id:
            raise ValidationError({"edupartner_id": _("This query parameter is required.")})

        pk = self.kwargs.get("pk")
        try:
            UUID(str(pk))
        except (ValueError, TypeError):
            raise ValidationError({"pk": _("Must be a valid UUID.")})

        return get_object_or_404(
            CandidateProfile.objects
            .select_related("candidate", "candidate__faculty", "candidate__faculty__domain", "candidate__edupartner"),
            pk=pk,
            candidate__edupartner_id=edupartner_id,
        )

    def retrieve(self, request, *args, **kwargs):
        edupartner_id = request.query_params.get("edupartner_id")
        pk = kwargs["pk"]
        cache_key = f"student_detail:{edupartner_id}:{pk}"

        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            cache.set(cache_key, response.data, self.CACHE_TTL)
        return response


students = StudentListAPIView.as_view()
student_detail = StudentDetailAPIView.as_view()
edu_partners = EduPartnerListAPIView.as_view()
edu_partners_type = EduPartnersTypeListAPIView.as_view()
faculties = FacultyListAPIView.as_view()
subjects = SubjectListAPIView.as_view()
