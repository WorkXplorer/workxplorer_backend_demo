from .candidate import (
    create_candidate_profile_view,
)
from .citizenship import citizenship_list_view
from .recruiter import (
    recruiter_profile_list_view,
    recruiter_level_update_view,
)
from .common import my_profile_view
from .company import about_company_view, company_info_view, company_public_detail_view
from .registration import register_recruiter_admin_view

__all__ = [
    "citizenship_list_view",
    "create_candidate_profile_view",
    "recruiter_profile_list_view",
    "my_profile_view",
    "recruiter_level_update_view",
    "about_company_view",
    "company_info_view",
    "company_public_detail_view",
    "register_recruiter_admin_view",
]
