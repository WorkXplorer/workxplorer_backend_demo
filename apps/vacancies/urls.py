# apps/vacancies/urls.py
from django.urls import path
from .views import (
    vacancy_list_view,
    favourite_vacancy_list_view,
    toggle_favourite_vacancy_view,
    create_vacancy_view,
    recruiter_vacancy_list_view,
    retrieve_vacancy_view,
    archive_vacancy_view,
    delete_vacancy_view,
    update_vacancy_view,
    inactive_vacancy_list_view,
    end_vacancy_view_session_view,
    vacancy_status_choices_view,                
)

urlpatterns = [
    # Public vacancy listing - all active vacancies
    path("", vacancy_list_view, name="vacancy-list"),
    # List favourite vacancies for authenticated candidate
    path("favourites/", favourite_vacancy_list_view, name="favourite-vacancy-list"),
    # Get vacancy by its id
    path("<uuid:id>/", retrieve_vacancy_view, name="retrieve-vacancy"),
    # Toggle favourite status for a vacancy (candidate only)
    path(
        "<uuid:id>/favourite/toggle/",
        toggle_favourite_vacancy_view,
        name="toggle-favourite-vacancy",
    ),
    # End vacancy view session
    path(
        "end-session/<uuid:pk>/",
        end_vacancy_view_session_view,
        name="end-vacancy-view-session",
    ),
    # Create new vacancy - requires recruiter authentication
    path("create/", create_vacancy_view, name="create-vacancy"),
    # List vacancies created by the current recruiter
    path("my-vacancies/", recruiter_vacancy_list_view, name="recruiter-vacancy-list"),
    # Archive (soft delete) a vacancy by id
    path("archive/<uuid:id>/", archive_vacancy_view, name="archive-vacancy"),
    # Delete a vacancy by id
    path("delete/<uuid:id>/", delete_vacancy_view, name="delete-vacancy"),
    # Update a vacancy by id
    path("update/<uuid:id>/", update_vacancy_view, name="update-vacancy"),
    # List inactive (archived) vacancies for the current recruiter
    path("inactive/", inactive_vacancy_list_view, name="inactive-vacancy-list"),
    # Get vacancy status choices
    path("status-choices/", vacancy_status_choices_view, name="vacancy-status-choices"),
]
