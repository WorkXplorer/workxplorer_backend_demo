from django.urls import path

from apps.hr_templates.views import TemplateListCreateView, TemplateDetailView, VariableListView

urlpatterns = [
    path(
        "templates/",
        TemplateListCreateView.as_view(),
        name="template-list-create",
    ),
    path(
        "templates/<uuid:template_id>/",
        TemplateDetailView.as_view(),
        name="template-detail",
    ),
    path(
        "variables/",
        VariableListView.as_view(),
        name="template-variables",
    ),
]
