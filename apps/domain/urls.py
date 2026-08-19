from django.urls import path
from .views import (
    domain_detail_view,
    domain_list_names_view,
    hr_created_profession_detail_view as hr_detail_view,
    hr_created_profession_list_create_view as hr_list_create_view,
)

urlpatterns = [
    # Retrieve, Update, Delete
    path("<int:pk>/", domain_detail_view, name="domain-detail"),
    # Lightweight list for dropdowns
    path("list-names/", domain_list_names_view, name="domain-list-names"),
    # HR Created Professions
    path(
        "hr-professions/", hr_list_create_view, name="hr-created-profession-list-create"
    ),
    path(
        "hr-professions/<int:profession_id>/",
        hr_detail_view,
        name="hr-created-profession-detail",
    ),
]
