from .list import (
    vacancy_list_view,
    recruiter_vacancy_list_view,
    inactive_vacancy_list_view,
)
from .detail import retrieve_vacancy_view
from .crud import (
    create_vacancy_view,
    update_vacancy_view,
    archive_vacancy_view,
    delete_vacancy_view,
)
from .favourite import (
    favourite_vacancy_list_view,
    toggle_favourite_vacancy_view,
)
from .choices import vacancy_status_choices_view
from .session import end_vacancy_view_session_view

__all__ = [
    "vacancy_list_view",
    "favourite_vacancy_list_view",
    "toggle_favourite_vacancy_view",
    "create_vacancy_view",
    "recruiter_vacancy_list_view",
    "retrieve_vacancy_view",
    "archive_vacancy_view",
    "delete_vacancy_view",
    "update_vacancy_view",
    "inactive_vacancy_list_view",
    "end_vacancy_view_session_view",
    "vacancy_status_choices_view",
]
