from django.urls import path
from .views import (
    general_user_register_view,
    candidate_register_view,
    recruiter_register_view,
    request_password_reset_view,
    reset_password_confirm_view,
    set_password_view,
    company_create_view,
    company_list_view,
    company_detail_view,
    company_profile_create_view,
    recruiter_levels_view,
    recruiter_approval_view,
    recruiter_rejection_view,
    user_delete_view,
    account_delete_view,
    validate_token,
    status
)

urlpatterns = [
    path("register/general/", general_user_register_view, name="register-general"),
    path("delete/<uuid:id>/", user_delete_view, name="user-delete"),
    # Self-service account deletion (candidates only)
    path("delete/me/", account_delete_view, name="account-delete"),
    path("register/candidate/", candidate_register_view, name="register-candidate"),
    path("register/recruiter/", recruiter_register_view, name="register-recruiter"),
    path(
        "reset-password/request/",
        request_password_reset_view,
        name="reset-password-request",
    ),
    path(
        "reset-password/confirm/",
        reset_password_confirm_view,
        name="reset-password-confirm",
    ),
    # Unified set-password endpoint (auto-detects candidate or recruiter)
    # Now this endpoint is not used, but we keep it for potential future use or reference.
    path(
        "set-password/",
        set_password_view,
        name="set-password",
    ),
    # Company endpoints
    path("companies/", company_list_view, name="company-list"),
    path("companies/create/", company_create_view, name="company-create"),
    path("companies/<uuid:pk>/", company_detail_view, name="company-detail"),
    # Company Profile endpoint
    path(
        "companies/profile/create/",
        company_profile_create_view,
        name="company-profile-create",
    ),
    # Recruiter Levels endpoint
    path("recruiter/levels/", recruiter_levels_view, name="recruiter-levels"),
    # Recruiter Approval endpoint
    path("recruiter/approve/", recruiter_approval_view, name="recruiter-approve"),
    # Recruiter Rejection endpoint
    path("recruiter/reject/", recruiter_rejection_view, name="recruiter-reject"),
    path("validate-token/", validate_token, name="validate-token"),
    path("status/", status, name="candidate-status"),
]
