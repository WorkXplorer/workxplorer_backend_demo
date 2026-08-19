"""v2 application views package."""

from .recruiter import (
    update_application_status_view,
)
from .kanban import kanban_view
from .candidate_applications import kanban_candidate_applications_view
from .status import (
    status_category_list_view,
    company_status_list_view,
    company_status_create_view,
    company_status_update_view,
    company_status_archive_view,
    company_status_reorder_view,
)
from .ai_evaluation import ai_evaluation_view
from .ai_revaluation import ai_revaluation_view

__all__ = [
    # Recruiter
    "update_application_status_view",
    # Kanban
    "kanban_view",
    "kanban_candidate_applications_view",
    # Status management
    "status_category_list_view",
    "company_status_list_view",
    "company_status_create_view",
    "company_status_update_view",
    "company_status_archive_view",
    "company_status_reorder_view",
    # AI Evaluation
    "ai_evaluation_view",
    # AI Revaluation
    "ai_revaluation_view",
]
