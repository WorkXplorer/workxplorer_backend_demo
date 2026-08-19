from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, OpenApiResponse
from apps.authentication.models import Company, Recruiter
from apps.authentication.serializers import CompanySerializer
from apps.profiles.models import RecruiterProfile, CompanyProfile
from ..serializers.company import AboutCompanySerializer, CompanyPublicDetailSerializer
from core.responses import APIResponse
from utils import IsAdminRecruiter, IsRecruiterPermission


class AboutCompanyView(generics.RetrieveUpdateAPIView):
    """
    View for retrieving and updating company information.
    GET: Available to all recruiters (Admin, Manager, Recruiter).
    PUT/PATCH: Only available to Admin recruiters.
    """

    serializer_class = AboutCompanySerializer

    def get_queryset(self):
        """Optimize queryset with select_related"""
        return CompanyProfile.objects.select_related(
            'company',
            'company__domain'
        )

    def get_permissions(self):
        """Set permissions based on request method"""
        if self.request.method in ['PUT', 'PATCH']:
            permission_classes = [IsAdminRecruiter]
        else:
            permission_classes = [IsRecruiterPermission]
        return [permission() for permission in permission_classes]

    def get_object(self):
        """Get the company profile for the current user's company with optimized queries"""
        user = self.request.user
        if user.is_recruiter is False:
            raise PermissionDenied("User is not a recruiter")

        # Get recruiter with company in a single query
        recruiter = get_object_or_404(
            Recruiter.objects.select_related('company', 'company__domain'),
            email=user.email
        )
        company = recruiter.company

        if not company:
            raise PermissionDenied("Recruiter does not belong to any company")

        # Get first recruiter with their profile for email and phone
        # Use Prefetch to optimize the query since recruiterprofile is a reverse FK
        first_recruiter = Recruiter.objects.filter(
            company=company
        ).prefetch_related(
            Prefetch('recruiterprofile_set', queryset=RecruiterProfile.objects.all())
        ).order_by('date_joined').first()

        # If first_recruiter exists, get the first profile
        if first_recruiter:
            profiles = list(first_recruiter.recruiterprofile_set.all())
            if profiles:
                first_recruiter._recruiter_profile = profiles[0]

        # Get or create company profile with optimized query
        try:
            company_profile = self.get_queryset().get(company=company)
        except CompanyProfile.DoesNotExist:
            company_profile = CompanyProfile.objects.create(
                company=company,
                description='',
                address='',
                website='',
            )
            # Manually set the related objects to avoid additional queries
            company_profile.company = company

        # Attach first recruiter data to avoid N+1 queries in serializer
        company_profile._first_recruiter = first_recruiter

        return company_profile

    @extend_schema(
        summary="Get Company Information",
        description="Retrieve complete company information including profile details, specialization domain, email, and phone. Available to all recruiters.",
        responses={
            200: AboutCompanySerializer,
            403: OpenApiResponse(description="Permission denied - user is not a recruiter"),
            404: OpenApiResponse(description="Company or company profile not found")
        },
        operation_id="get_company_info",
        tags=["Company Profile"]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update Company Information",
        description="Update company profile information including description, address, website, and logo. Only available to Admin recruiters.",
        request=AboutCompanySerializer,
        responses={
            200: AboutCompanySerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied - user is not an admin recruiter")
        },
        operation_id="update_company_info",
        tags=["Company Profile"]
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        summary="Partially Update Company Information",
        description="Partially update company profile information. Only available to Admin recruiters.",
        request=AboutCompanySerializer,
        responses={
            200: AboutCompanySerializer,
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Permission denied - user is not an admin recruiter")
        },
        operation_id="patch_company_info",
        tags=["Company Profile"]
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class CompanyInfoView(generics.RetrieveAPIView):
    """
    Public company information detail endpoint.
    Accessible without authentication. Returns basic company details
    including name, domain, photo, email, phone, description, and address.
    """

    queryset = Company.objects.select_related("domain").prefetch_related(
        Prefetch(
            "companyprofile",
            queryset=CompanyProfile.objects.all(),
            to_attr="company_profiles",
        ),
    )
    serializer_class = CompanySerializer
    permission_classes = [AllowAny]

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        obj = get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        summary=_("Get Company Information"),
        description=_("Retrieve basic company information. Publicly accessible without authentication."),
        responses={
            200: CompanySerializer,
            404: OpenApiResponse(description=str(_("Company not found."))),
        },
        operation_id="get_public_company_info",
        tags=["Company Info"],
    )
    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return APIResponse.success(data=serializer.data)


# View instance for URL routing
about_company_view = AboutCompanyView.as_view()


class CompanyPublicDetailView(generics.RetrieveAPIView):
    """Public company detail endpoint — returns brand fields, stats and page type."""

    serializer_class = CompanyPublicDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'company__id'
    lookup_url_kwarg = 'company_id'

    def get_object(self):
        company_id = self.kwargs.get('company_id')
        profile = (
            CompanyProfile.objects
            .select_related('company')
            .prefetch_related('gallery_images')
            .filter(company__id=company_id)
            .first()
        )
        if not profile:
            raise NotFound("Company not found.")
        return profile


company_info_view = CompanyInfoView.as_view()
company_public_detail_view = CompanyPublicDetailView.as_view()
