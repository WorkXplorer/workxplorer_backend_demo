from django.urls import path
from .views import (
    apply_to_vacancy_view,
    candidate_application_list_view,
    withdraw_application_view,
    application_detail_view,
    update_application_status_view,
    reapply_to_vacancy_view,
    accept_offer_view,
    reject_offer_view,
    application_status_list_view,
    company_candidates_list_view,
    company_candidate_applications_view,
    hired_candidates_list_view,
    trigger_daily_report_view,
)

urlpatterns = [
    # General applications list (redirects based on user type)
    path("", candidate_application_list_view, name="applications-list"),
    # Candidate endpoints
    path("apply/", apply_to_vacancy_view, name="apply-to-vacancy"),
    path("<uuid:application_id>/", application_detail_view, name="application-detail"),
    path(
        "<uuid:application_id>/withdraw/",
        withdraw_application_view,
        name="withdraw-application",
    ),
    path(
        "<uuid:application_id>/reapply/",
        reapply_to_vacancy_view,
        name="reapply-to-vacancy",
    ),
    path(
        "<uuid:application_id>/accept-offer/",
        accept_offer_view,
        name="accept-offer",
    ),
    path(
        "<uuid:application_id>/reject-offer/",
        reject_offer_view,
        name="reject-offer",
    ),
    # Recruiter endpoints
    # Also handles Kanban move operations with kanban_position field
    path(
        "<uuid:application_id>/update-status/",
        update_application_status_view,
        name="update-application-status",
    ),
    path(
        "statuses/",
        application_status_list_view,
        name="application-statuses",
    ),
    path(
        "company-candidates/",
        company_candidates_list_view,
        name="company-candidates",
    ),
    # All applications of one candidate to the company's vacancies
    # (candidates-list detail dropdown), best AI match first
    path(
        "company-candidates/<uuid:candidate_id>/applications/",
        company_candidate_applications_view,
        name="company-candidate-applications",
    ),
    # Hired candidates endpoint (admin only)
    path(
        "hired-candidates/",
        hired_candidates_list_view,
        name="hired-candidates",
    ),
    # Internal: Telegram bot /report command (shared-secret auth)
    path(
        "reports/daily/trigger/",
        trigger_daily_report_view,
        name="trigger-daily-report",
    ),
]
