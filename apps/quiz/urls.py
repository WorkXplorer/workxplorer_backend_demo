from django.urls import path
from .views import (
    quiz_type_list_view,
    question_list_view,
    calculate_quiz_result_view,
    determine_domain_view,
    latest_quiz_result_view,
)

urlpatterns = [
    path("types/", quiz_type_list_view, name="quiz-type-list"),
    path("questions/", question_list_view, name="question-list"),
    path("responses/", calculate_quiz_result_view, name="response-list"),
    path("determine-domain/", determine_domain_view, name="determine-domain"),
    path("results/latest/", latest_quiz_result_view, name="latest-quiz-result"),
]
