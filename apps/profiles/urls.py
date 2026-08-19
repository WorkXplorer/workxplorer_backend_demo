from django.urls import path

from .views import (
    citizenship_list_view,
    recruiter_profile_list_view,
    create_candidate_profile_view,
    my_profile_view,
    recruiter_level_update_view,
    about_company_view,
    company_info_view,
    company_public_detail_view,
    register_recruiter_admin_view,
)

urlpatterns = [
    path("citizenships/", citizenship_list_view, name="citizenship-list"),
    path("recruiter/list/", recruiter_profile_list_view, name="recruiter-profile-list"),
    path(
        "candidate/create/",
        create_candidate_profile_view,
        name="create-candidate-profile",
    ),
    # Admin-only recruiter registration (create)
    path(
        "register/recruiter/admin/",
        register_recruiter_admin_view,
        name="register-recruiter-admin",
    ),
    path(
        "recruiter/update/<uuid:recruiter_id>/",
        recruiter_level_update_view,
        name="recruiter-level-update",
    ),
    # About Company endpoint (GET and UPDATE)
    path(
        "company/about/",
        about_company_view,
        name="about-company-info",
    ),
    # Public company info detail
    path(
        "company/<uuid:pk>/",
        company_info_view,
        name="company-info",
    ),
    # My Profile endpoint (GET and UPDATE)
    path("me/", my_profile_view, name="my-profile-get-update"),
    # Public company detail
    path("companies/<uuid:company_id>/", company_public_detail_view, name="company-public-detail"),
]
