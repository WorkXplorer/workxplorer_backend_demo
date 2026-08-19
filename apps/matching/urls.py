from django.urls import path
from .views import match_resume_to_vacancies, match_vacancy_to_resumes

urlpatterns = [
    # Match resume to all vacancies
    path(
        "resume/<uuid:resume_id>/vacancies/",
        match_resume_to_vacancies,
        name="match-resume-to-vacancies",
    ),
    # Match vacancy to all resumes
    path(
        "vacancy/<uuid:vacancy_id>/resumes/",
        match_vacancy_to_resumes,
        name="match-vacancy-to-resumes",
    ),
]
