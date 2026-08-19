from rest_framework import generics
from rest_framework import serializers
from ..serializers import CandidateProfileSerializer, RecruiterProfileSerializer
from ..models import CandidateProfile
from apps.authentication.models import Candidate, Recruiter
from apps.profiles.models import RecruiterProfile
from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from utils import IsCandidatePermission, IsRecruiterPermission


class MyProfileView(generics.RetrieveUpdateAPIView):
    """
    View to retrieve or update the profile of the currently authenticated user.
    Supports both candidates and recruiters.
    """

    permission_classes = [
        IsAuthenticated,
        IsCandidatePermission | IsRecruiterPermission,
    ]

    def get_serializer_class(self):
        user = self.request.user

        if not hasattr(user, "is_candidate") or not hasattr(user, "is_recruiter"):
            raise Http404("User type attributes are not properly set.")

        if user.is_candidate:
            return CandidateProfileSerializer
        elif user.is_recruiter:
            return RecruiterProfileSerializer
        else:
            raise Http404(
                f"Unknown user type. is_candidate: {user.is_candidate}, is_recruiter: {user.is_recruiter}"
            )

    def get_object(self):
        user = self.request.user

        try:
            if user.is_candidate:
                return (
                    CandidateProfile.objects.select_related("candidate")
                    .filter(candidate__email=user.email)
                    .first()
                ) or self._raise_404("Candidate profile not found")

            if user.is_recruiter:
                return (
                    RecruiterProfile.objects.select_related("recruiter__company")
                    .prefetch_related("recruiter__company__companyprofile")
                    .filter(recruiter__email=user.email)
                    .first()
                ) or self._raise_404("Recruiter profile not found")

            else:
                raise Http404("Unknown user type")

        except (Candidate.DoesNotExist, Recruiter.DoesNotExist):
            raise Http404("User not found")

    @extend_schema(
        summary="Get My Profile",
        description="Retrieve the profile of the currently authenticated user. Returns candidate profile if user is a candidate, or recruiter profile if user is a recruiter.",
        responses={
            200: OpenApiResponse(
                description="User profile data",
                response=inline_serializer(
                    "MyProfileResponse",
                    fields={
                        "profile": serializers.JSONField(
                            help_text="CandidateProfileSerializer or RecruiterProfileSerializer output depending on user type"
                        ),
                    },
                ),
            ),
            404: OpenApiResponse(description="Profile not found for this user"),
        },
        operation_id="get_my_profile",
        tags=["Profile"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update My Profile",
        description="Update the complete profile of the currently authenticated user. "
                    "Sends CandidateProfileSerializer for candidates, RecruiterProfileSerializer for recruiters.",
        request=inline_serializer(
            "MyProfileUpdateRequest",
            fields={
                "full_name": serializers.CharField(required=False),
                "phone": serializers.CharField(required=False),
                "photo": serializers.ImageField(required=False),
                "address": serializers.CharField(required=False),
                "education": serializers.JSONField(required=False),
                "edupartner_id": serializers.UUIDField(required=False),
                "faculty_id": serializers.UUIDField(required=False),
                "citizenship_id": serializers.UUIDField(required=False),
                "date_of_birth": serializers.DateField(required=False),
                "github_url": serializers.URLField(required=False),
                "linkedin_url": serializers.URLField(required=False),
                "social_url": serializers.URLField(required=False),
                "telegram_url": serializers.URLField(required=False),
            },
        ),
        responses={
            200: OpenApiResponse(
                description="Updated profile data",
                response=inline_serializer(
                    "MyProfileUpdateResponse",
                    fields={"profile": serializers.JSONField()},
                ),
            ),
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Profile not found"),
        },
        operation_id="update_my_profile",
        tags=["Profile"],
    )
    def put(self, request, *args, **kwargs):
        if not self.get_object():
            raise Http404("You are not allowed to update this profile.")
        return super().put(request, *args, **kwargs)

    @extend_schema(
        summary="Partially Update My Profile",
        description="Partially update the profile of the currently authenticated user. "
                    "Supports the same fields as PUT but only applies provided fields.",
        request=inline_serializer(
            "MyProfilePatchRequest",
            fields={
                "full_name": serializers.CharField(required=False),
                "phone": serializers.CharField(required=False),
                "photo": serializers.ImageField(required=False),
                "address": serializers.CharField(required=False),
                "education": serializers.JSONField(required=False),
                "edupartner_id": serializers.UUIDField(required=False),
                "faculty_id": serializers.UUIDField(required=False),
                "citizenship_id": serializers.UUIDField(required=False),
                "date_of_birth": serializers.DateField(required=False),
                "github_url": serializers.URLField(required=False),
                "linkedin_url": serializers.URLField(required=False),
                "social_url": serializers.URLField(required=False),
                "telegram_url": serializers.URLField(required=False),
            },
        ),
        responses={
            200: OpenApiResponse(
                description="Partially updated profile data",
                response=inline_serializer(
                    "MyProfilePatchResponse",
                    fields={"profile": serializers.JSONField()},
                ),
            ),
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Profile not found"),
        },
        operation_id="patch_my_profile",
        tags=["Profile"],
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def _raise_404(self, message):
        raise Http404(message)


my_profile_view = MyProfileView.as_view()
