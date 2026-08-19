from rest_framework import generics
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, inline_serializer

from ..serializers import CandidateProfileSerializer
from ..models import CandidateProfile
from rest_framework.permissions import AllowAny
from apps.authentication.transitions import update_candidate_step, CREATE_PROFILE


@extend_schema_view(
    post=extend_schema(
        summary="Create candidate profile",
        description="Create a candidate profile with personal details, education, and social links. "
                    "The profile links to a previously registered candidate account. "
                    "Only one profile per candidate is allowed.",
        request=CandidateProfileSerializer,
        responses={
            201: OpenApiResponse(
                response=CandidateProfileSerializer,
                description="Profile created successfully",
            ),
            400: OpenApiResponse(
                response=inline_serializer(
                    "ValidationError",
                    fields={
                        "success": serializers.BooleanField(default=False),
                        "error": inline_serializer(
                            "ProfileValidationErrorDetail",
                            fields={
                                "code": serializers.CharField(default="VALIDATION_ERROR"),
                                "message": serializers.CharField(),
                                "field_errors": serializers.DictField(
                                    child=serializers.ListField(child=serializers.CharField()),
                                ),
                            },
                        ),
                        "timestamp": serializers.DateTimeField(),
                    },
                ),
                description="Validation error — duplicate profile, missing edupartner, etc.",
            ),
        },
    ),
)
class CreateCandidateProfileView(generics.CreateAPIView):
    """
    View to create a new candidate profile. Accessible by anyone.
    """

    queryset = CandidateProfile.objects.select_related("candidate", "citizenship").all()
    serializer_class = CandidateProfileSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        profile = serializer.save()
        update_candidate_step(profile.candidate, CREATE_PROFILE)



create_candidate_profile_view = CreateCandidateProfileView.as_view()
