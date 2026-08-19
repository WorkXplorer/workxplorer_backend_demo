from .user_management import user_delete_view, account_delete_view
from .registration import (
    candidate_register_view,
    recruiter_register_view,
    general_user_register_view,
    recruiter_approval_view,
    recruiter_rejection_view,
)
from .reset_password import (
    request_password_reset_view,
    reset_password_confirm_view,
    set_password_view,
)
from .company import (
    company_create_view,
    company_list_view,
    company_detail_view,
    company_profile_create_view,
)
from .recruiter_level import recruiter_levels_view
from .validate_token import validate_token
from .candidate import status
from .oauth_views import GoogleOAuthCandidateView

__all__ = [
    "general_user_register_view",
    "user_delete_view",
    "account_delete_view",
    "candidate_register_view",
    "recruiter_register_view",
    "request_password_reset_view",
    "reset_password_confirm_view",
    "company_create_view",
    "company_list_view",
    "company_detail_view",
    "company_profile_create_view",
    "recruiter_levels_view",
    "recruiter_approval_view",
    "recruiter_rejection_view",
    "validate_token",
    "set_password_view",
    "status",
    "GoogleOAuthCandidateView",
]
