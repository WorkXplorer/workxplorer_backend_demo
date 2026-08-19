from .candidate import (
    candidate_application_list_view,
    withdraw_application_view,
    apply_to_vacancy_view,
    reapply_to_vacancy_view,
    accept_offer_view,
    reject_offer_view,
)
from .recruiter import (
    update_application_status_view,
    application_status_list_view,
    company_candidates_list_view,
    company_candidate_applications_view,
    hired_candidates_list_view,
)
from .shared import application_detail_view
from .reports import trigger_daily_report_view

__all__ = [
    # Candidate views
    "candidate_application_list_view",
    "withdraw_application_view",
    "apply_to_vacancy_view",
    "reapply_to_vacancy_view",
    "accept_offer_view",
    "reject_offer_view",
    # Recruiter views
    "update_application_status_view",
    "application_status_list_view",
    "company_candidates_list_view",
    "company_candidate_applications_view",
    "hired_candidates_list_view",
    # Shared views
    "application_detail_view",
    # Internal report endpoints
    "trigger_daily_report_view",
]
