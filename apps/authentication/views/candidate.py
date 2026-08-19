from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample, inline_serializer

from apps.authentication.transitions import (
    get_candidate_progress,
    sync_candidate_resume_step,
    CREATE_RESUME,
)
from core.responses import APIResponse
from utils.language import get_request_language


class CandidateStatusAPIView(APIView):
    """
    API endpoint to retrieve candidate's onboarding progress and status.
    Returns structured progress data including completed steps and current position.
    """
    
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Get candidate's onboarding progress and status",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "CandidateProgressData",
                    fields={
                        "progress": serializers.IntegerField(),
                        "current_step": serializers.CharField(),
                        "status": serializers.CharField(),
                        "status_label": serializers.CharField(),
                        "steps": serializers.ListField(
                            child=inline_serializer(
                                "ProgressStep",
                                fields={
                                    "code": serializers.CharField(),
                                    "label": serializers.CharField(),
                                    "completed": serializers.BooleanField(),
                                    "completed_at": serializers.DateTimeField(allow_null=True),
                                    "url": serializers.CharField(),
                                },
                            ),
                        ),
                    },
                ),
                description="Candidate progress retrieved successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "message": "Operation completed successfully",
                            "data": {
                                "progress": 0,
                                "current_step": "string",
                                "status": "string",
                                "status_label": "string",
                                "steps": [
                                    {
                                        "code": "string",
                                        "label": "string",
                                        "completed": True,
                                        "completed_at": "2026-04-17T12:27:44.937Z",
                                        "url": "string"
                                    }
                                ]
                            },
                            "timestamp": "2026-02-24T10:00:00+00:00"
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            403: OpenApiResponse(
                response=inline_serializer(
                    "ErrorResponse",
                    fields={
                        "success": serializers.BooleanField(default=False),
                        "error": inline_serializer(
                            "ErrorDetail",
                            fields={
                                "code": serializers.CharField(),
                                "message": serializers.CharField(),
                            },
                        ),
                        "timestamp": serializers.DateTimeField(),
                    },
                ),
                description="User is not a candidate",
                examples=[
                    OpenApiExample(
                        "Not a Candidate",
                        value={
                            "success": False,
                            "error": {
                                "code": "PERMISSION_DENIED",
                                "message": "Only candidates can access this endpoint"
                            },
                            "timestamp": "2024-01-15T10:35:00Z"
                        },
                        status_codes=["403"],
                    )
                ],
            ),
        },
    )
    def get(self, request):
        if not hasattr(request.user, "candidate"):
            raise PermissionDenied(_("Only candidates can access this endpoint"))

        candidate = request.user.candidate
        sync_candidate_resume_step(candidate)
        language = get_request_language()
        data = get_candidate_progress(candidate, language=language)
        data["resume_step_completed"] = any(
            step["code"] == CREATE_RESUME and step["completed"]
            for step in data["steps"]
        )

        return APIResponse.success(
            data=data,
            message=_("Candidate status retrieved successfully"),
        )


status = CandidateStatusAPIView.as_view()
