from django.urls import path

from .views import (
    GenerateTestAPIView,
    StartTestAPIView,
    SubmitAttemptAPIView,
    AttemptResultAPIView,
    CandidateAttemptsAPIView,
)

urlpatterns = [
    path(
        "generate/",
        GenerateTestAPIView.as_view(),
        name="skill-test-generate",
    ),
    path(
        "<uuid:test_id>/start/",
        StartTestAPIView.as_view(),
        name="skill-test-start",
    ),
    path(
        "attempts/<uuid:attempt_id>/submit/",
        SubmitAttemptAPIView.as_view(),
        name="skill-test-submit-attempt",
    ),
    path(
        "attempts/<uuid:attempt_id>/result/",
        AttemptResultAPIView.as_view(),
        name="skill-test-attempt-result",
    ),
    path(
        "attempts/",
        CandidateAttemptsAPIView.as_view(),
        name="skill-test-candidate-attempts",
    ),
]
