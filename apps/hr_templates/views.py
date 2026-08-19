from rest_framework import generics, status
from rest_framework.permissions import AllowAny

from django.utils.translation import gettext as _

from core.responses import APIResponse
from utils.language import get_request_language
from utils.recruiter_permission import IsRecruiterPermission
from utils.view_mixins import RecruiterMixin

from apps.hr_templates.models import Template
from apps.hr_templates.serializers import TemplateSerializer
from apps.subscriptions.permissions import CanCreateTemplate
from apps.hr_templates.constants import VARIABLE_INFO, get_localized_form


class TemplateListCreateView(RecruiterMixin, generics.ListCreateAPIView):
    """
    GET  - List all templates for the recruiter's company.
    POST - Create a new template for the recruiter's company.

    Only accessible by authenticated recruiters.
    Can be filtered by template type and application status.

    Subscription limits enforced on POST:
    - CanCreateTemplate: checks max status change templates for the plan
    """
    serializer_class = TemplateSerializer
    permission_classes = [IsRecruiterPermission, CanCreateTemplate]

    def get_queryset(self):
        recruiter = self.get_recruiter()
        queryset = Template.objects.filter(company=recruiter.company).select_related(
            "application_status"
        )

        template_type = self.request.query_params.get("template_type", None)
        if template_type:
            queryset = queryset.filter(template_type=template_type)

        status_id = self.request.query_params.get("status_id", None)
        if status_id:
            queryset = queryset.filter(application_status_id=status_id)

        return queryset

    def perform_create(self, serializer):
        recruiter = self.get_recruiter()
        serializer.save(company=recruiter.company)


class TemplateDetailView(RecruiterMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET    - Retrieve a single template.
    PUT    - Fully update a template.
    PATCH  - Partially update a template.
    DELETE - Delete a template.

    Only accessible by authenticated recruiters.
    Scoped to the recruiter's company to prevent cross-company access.
    """
    serializer_class = TemplateSerializer
    permission_classes = [IsRecruiterPermission]
    lookup_url_kwarg = "template_id"

    def get_queryset(self):
        recruiter = self.get_recruiter()
        return Template.objects.filter(company=recruiter.company).select_related(
            "application_status"
        )

    def perform_update(self, serializer):
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        self.perform_destroy(instance)
        return APIResponse.success(
            data=data,
            message=_("Template deleted successfully"),
            status_code=status.HTTP_200_OK,
        )


class VariableListView(generics.GenericAPIView):
    # ponytail: exposes only static variable metadata (key, description, localized_form)
    # no sensitive data — frontend needs this before authentication to render UI
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        lang = get_request_language()
        variables = []
        for info in VARIABLE_INFO:
            variables.append({
                "key": info["key"],
                "description": info["description"],
                "localized_form": get_localized_form(info["key"], lang),
            })
        return APIResponse.success(data={"variables": variables})
