from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, extend_schema_view

from core.responses import APIResponse

from apps.conversations.models import ApplicationDiscussion
from apps.conversations.serializers.discussions import (
    ApplicationDiscussionSerializer,
)
from apps.applications.models import JobApplication
from utils.recruiter_permission import IsRecruiterPermission
from utils.view_mixins import RecruiterCompanyMixin


@extend_schema_view(
    list=extend_schema(
        summary="List discussions for an application",
        description="List all internal discussions for an application. "
                    "Only recruiters from the same company can view.",
    ),
    create=extend_schema(
        summary="Create a discussion",
        description="Create a new internal discussion about an application.",
    ),
)
class DiscussionListCreateView(RecruiterCompanyMixin, generics.ListCreateAPIView):
    serializer_class = ApplicationDiscussionSerializer
    permission_classes = [IsRecruiterPermission]

    def _get_application(self):
        if not hasattr(self, "_application"):
            application_id = self.kwargs["application_id"]
            self._application = get_object_or_404(
                JobApplication.objects.select_related("vacancy__company"),
                id=application_id,
            )
        return self._application

    def get_queryset(self):
        app = self._get_application()
        recruiter, company = self.get_recruiter_and_company()

        if app.vacancy.company_id != company.id:
            raise PermissionDenied(
                _("You are not authorized to access discussions for this application")
            )

        return (
            ApplicationDiscussion.objects
            .filter(application_id=app.id)
            .select_related("recruiter", "recruiter__company")
            .prefetch_related("recruiter__recruiterprofile_set")
            .order_by("created_at")
        )

    def perform_create(self, serializer):
        app = self._get_application()
        recruiter, company = self.get_recruiter_and_company()

        if app.vacancy.company_id != company.id:
            raise PermissionDenied(
                _("You are not authorized to discuss this application")
            )

        serializer.save(application=app, recruiter=recruiter, status_snapshot=app.status)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return APIResponse.success(data=serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return APIResponse.created(
            data=serializer.data,
            message=_("Discussion created successfully"),
        )


@extend_schema_view(
    retrieve=extend_schema(
        summary="Retrieve a discussion",
        description="Retrieve a specific internal discussion.",
    ),
    update=extend_schema(
        summary="Update a discussion",
        description="Update a discussion. Only the author can edit.",
    ),
    partial_update=extend_schema(
        summary="Partially update a discussion",
        description="Partially update a discussion. Only the author can edit.",
    ),
    destroy=extend_schema(
        summary="Delete a discussion",
        description="Delete a discussion. Only the author can delete.",
    ),
)
class DiscussionDetailView(RecruiterCompanyMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ApplicationDiscussionSerializer
    permission_classes = [IsRecruiterPermission]
    lookup_url_kwarg = "id"

    def _get_application(self):
        if not hasattr(self, "_application"):
            application_id = self.kwargs["application_id"]
            self._application = get_object_or_404(
                JobApplication.objects.select_related("vacancy__company"),
                id=application_id,
            )
        return self._application

    def get_queryset(self):
        app = self._get_application()
        recruiter, company = self.get_recruiter_and_company()

        if app.vacancy.company_id != company.id:
            raise PermissionDenied(
                _("You are not authorized to access discussions for this application")
            )

        return (
            ApplicationDiscussion.objects
            .filter(application_id=app.id)
            .select_related("recruiter", "recruiter__company")
            .prefetch_related("recruiter__recruiterprofile_set")
        )

    def perform_update(self, serializer):
        if serializer.instance.recruiter_id != self.request.user.id:
            raise PermissionDenied(
                _("You can only edit your own discussions")
            )
        serializer.save(is_edited=True)

    def perform_destroy(self, instance):
        if instance.recruiter_id != self.request.user.id:
            raise PermissionDenied(
                _("You can only delete your own discussions")
            )
        instance.delete()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return APIResponse.success(data=serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return APIResponse.success(
            data=serializer.data,
            message=_("Discussion updated successfully"),
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return APIResponse.success(
            message=_("Discussion deleted successfully"),
        )


discussion_list_create_view = DiscussionListCreateView.as_view()
discussion_detail_view = DiscussionDetailView.as_view()
