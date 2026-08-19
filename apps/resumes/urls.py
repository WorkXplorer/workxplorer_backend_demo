from django.urls import path

from .views import (
    retrieve_resume_view,
    create_resume_view,
    update_resume_view,
    candidate_resume_list_view,
    work_status_list_view,
    set_main_resume_view,
    delete_resume_view,
    generate_resume_view,
    resume_generation_status_view,
    resume_generation_usage_view,
)

urlpatterns = [
    # Get resume by its id
    path("<uuid:id>/", retrieve_resume_view, name="retrieve-resume"),
    # Create new resume - requires candidate authentication
    path("create/", create_resume_view, name="create-candidate-resume-profile"),
    # Update existing resume - requires candidate authentication and ownership
    path("<uuid:id>/update/", update_resume_view, name="update-resume"),
    # Delete existing resume - requires candidate authentication and ownership
    path("<uuid:id>/delete/", delete_resume_view, name="delete-resume"),
    # List resumes created by the current candidate
    path("my-resumes/", candidate_resume_list_view, name="candidate-resume-list"),
    # List all work status choices
    path("work-status/", work_status_list_view, name="work-status-list"),
    # Set resume as main
    path("<uuid:id>/set-main/", set_main_resume_view, name="set-main-resume"),
    # AI-powered resume generation
    path("generate/", generate_resume_view, name="generate-resume"),
    # Check resume generation status
    path("generate-status/<str:job_id>/", resume_generation_status_view, name="resume-generation-status"),
    # Get current candidate's AI generation usage for the current month
    path("generate-usage/", resume_generation_usage_view, name="resume-generation-usage"),
]
