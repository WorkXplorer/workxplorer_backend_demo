"""
v2 URL configuration for the applications app.

8 endpoints:

Core (3):
  PATCH  <id>/update-status/          — recruiter: update status/position
  GET    kanban/                       — recruiter: kanban board
  GET    <id>/ai-evaluation/           — recruiter: get AI evaluation for application

Status management (5):
  GET         status-categories/             — list analytics categories (read-only)
  GET         company-statuses/              — list company statuses
  POST        company-statuses/create/       — create a company status
  PATCH       company-statuses/<id>/         — update a company status
  POST        company-statuses/<id>/archive/ — archive with optional batch-move
  PATCH       company-statuses/reorder/      — bulk reorder
"""

from django.urls import path

from .views.v2 import (
    # Core
    update_application_status_view,
    kanban_view,
    kanban_candidate_applications_view,
    ai_evaluation_view,
    # Status management
    status_category_list_view,
    company_status_list_view,
    company_status_create_view,
    company_status_update_view,
    company_status_archive_view,
    company_status_reorder_view,
    # AI Revaluation
    ai_revaluation_view,
)

urlpatterns = [
    # ------------------------------------------------------------------ #
    # Core application endpoints                                          #
    # ------------------------------------------------------------------ #
    path(
        "<uuid:application_id>/update-status/",
        update_application_status_view,
        name="v2-update-application-status",
    ),
    path("kanban/", kanban_view, name="v2-kanban-applications"),
    # All applications of one candidate to the company's vacancies
    # (kanban card dropdown), best AI match first
    path(
        "kanban/candidates/<uuid:candidate_id>/applications/",
        kanban_candidate_applications_view,
        name="v2-kanban-candidate-applications",
    ),
    path(
        "<uuid:application_id>/ai-evaluation/",
        ai_evaluation_view,
        name="v2-application-ai-evaluation",
    ),

    # ------------------------------------------------------------------ #
    # Status management                                                   #
    # ------------------------------------------------------------------ #
    path(
        "status-categories/",
        status_category_list_view,
        name="v2-status-categories",
    ),
    path(
        "company-statuses/",
        company_status_list_view,
        name="v2-company-statuses-list",
    ),
    path(
        "company-statuses/create/",
        company_status_create_view,
        name="v2-company-statuses-create",
    ),
    path(
        "company-statuses/reorder/",
        company_status_reorder_view,
        name="v2-company-statuses-reorder",
    ),
    path(
        "company-statuses/<uuid:status_id>/",
        company_status_update_view,
        name="v2-company-status-detail",
    ),
    path(
        "company-statuses/<uuid:status_id>/archive/",
        company_status_archive_view,
        name="v2-company-status-archive",
    ),
    path(
        "ai-revaluation/",
        ai_revaluation_view,
        name="v2-ai-revaluation",
    ),
]
