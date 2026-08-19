from django.urls import path

from apps.edupartners.views import (
    edu_partners,
    edu_partners_type,
    faculties,
    subjects,
    vault_registration_view,
    vault_university_list_view,
    students,
    student_detail
)

urlpatterns = [
    path("", edu_partners, name="edu-partner-list"),
    path("students/", students, name="student-list"),
    path("students/<uuid:pk>/", student_detail, name="student-detail"),
    path("types/", edu_partners_type, name="edu-partner-types"),
    path("faculties/", faculties, name="faculty-list"),
    path("subjects/", subjects, name="subject-list"),
    path("vault/register/", vault_registration_view, name="vault-registration"),
    path("vault/universities/", vault_university_list_view, name="vault-universities"),
]
