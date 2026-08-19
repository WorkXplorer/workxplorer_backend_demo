from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from core.responses import APIResponse

from apps.profiles.serializers.recruiter import RecruiterLevelUpdateSerializer, RecruiterListSerializer

from apps.authentication.models import Recruiter
from apps.profiles.models import RecruiterProfile

from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import transaction
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
    OpenApiParameter,
)

from utils import IsAdminRecruiter
from config.pagination import CustomPagination
from django.utils.translation import gettext as _


class RecruiterProfileListView(generics.ListAPIView):
    """
    View to list recruiter profiles for the authenticated recruiter.
    Only recruiters can access this view, and they will see all recruiters belonging to their company,
    including themselves.
    Supports filtering by full_name via query parameter.
    """

    serializer_class = RecruiterListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="full_name",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter recruiters by full name (icontains).",
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user

        # Ensure the user is a recruiter
        if not hasattr(user, "is_recruiter") or not user.is_recruiter:
            raise ValidationError(_("User is not a recruiter"))

        company_id = getattr(user, "company_id", None)
        if company_id is None:
            recruiter = Recruiter.objects.only("company_id").filter(pk=user.id).first()
            if recruiter is None:
                raise ValidationError(_("Recruiter not found"))
            company_id = recruiter.company_id

        if not company_id:
            raise ValidationError(_("Recruiter does not belong to any company"))

        # Base queryset: all active recruiters belonging to the same company
        queryset = RecruiterProfile.objects.filter(
            recruiter__company_id=company_id,
            recruiter__is_waiting_approval=False,
        ).select_related("recruiter")

        # Filter by full_name if provided
        full_name = self.request.query_params.get("full_name")
        if full_name:
            queryset = queryset.filter(full_name__icontains=full_name)

        return queryset.order_by("recruiter__email")


class RecruiterLevelUpdateView(APIView):
    """
    API View for updating recruiter role (level)
    Only Admins can update other recruiters' levels.
    Available levels: Recruiter, Admin
    """

    permission_classes = [IsAdminRecruiter]

    @extend_schema(
        summary="Update recruiter role (level)",
        description=(
                "Allows an Admin to update another recruiter's role. "
                "Valid levels are: `Recruiter`, `Admin`. "
                "Prevents downgrading the last remaining Admin."
        ),
        parameters=[
            OpenApiParameter(
                name="recruiter_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="ID of the recruiter to update",
            )
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["Recruiter", "Admin"],
                        "example": "Admin",
                    }
                },
                "required": ["level"],
            }
        },
        responses={
            200: OpenApiResponse(
                description="Recruiter role successfully updated",
                response={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "message": {
                            "type": "string",
                            "example": "Recruiter role successfully updated",
                        },
                    },
                },
            ),
            400: OpenApiResponse(
                description="Invalid request or validation error",
                response={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "message": {"type": "string", "example": "Invalid data"},
                        "errors": {
                            "type": "object",
                            "example": {"level": ["Invalid choice"]},
                        },
                    },
                },
            ),
            404: OpenApiResponse(
                description="Recruiter not found",
                response={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "message": {"type": "string", "example": "Recruiter not found"},
                    },
                },
            ),
            500: OpenApiResponse(
                description="Unexpected server error",
                response={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "message": {
                            "type": "string",
                            "example": "An error occurred: ...",
                        },
                    },
                },
            ),
        },
        examples=[
            OpenApiExample(
                "Valid request", value={"level": "Manager"}, request_only=True
            ),
            OpenApiExample(
                "Successful response",
                value={
                    "success": True,
                    "message": "Recruiter role successfully updated",
                },
                response_only=True,
            ),
            OpenApiExample(
                "Error response (last admin)",
                value={
                    "success": False,
                    "message": "Cannot downgrade the last admin recruiter",
                },
                response_only=True,
            ),
        ],
    )
    def patch(self, request, recruiter_id):
        """
        Update recruiter role (Admin / Manager / Recruiter)
        """
        try:
            # Scope to admin's own company
            company_id = getattr(request.user, "company_id", None)
            if company_id is None:
                recruiter = Recruiter.objects.only("company_id").filter(pk=request.user.id).first()
                if recruiter is None:
                    return APIResponse.not_found(message=_("Admin recruiter not found"))
                company_id = recruiter.company_id

            # Find the recruiter profile to update — scoped to same company
            recruiter_profile = get_object_or_404(
                RecruiterProfile.objects.select_related("recruiter"),
                id=recruiter_id,
                recruiter__company_id=company_id,
            )

            serializer = RecruiterLevelUpdateSerializer(data=request.data)

            if serializer.is_valid():
                old_level = recruiter_profile.level
                new_level = serializer.validated_data["level"]

                # Prevent downgrading the last Admin — company-scoped
                if old_level == "Admin" and new_level != "Admin":
                    admin_count = RecruiterProfile.objects.filter(
                        level="Admin",
                        recruiter__company_id=company_id,
                    ).count()
                    if admin_count <= 1:
                        return APIResponse.bad_request(
                            message=_("Cannot downgrade the last admin recruiter")
                        )

                with transaction.atomic():
                    recruiter_profile.level = new_level
                    recruiter_profile.save()

                    cache.delete(
                        f"recruiter_admin_permission_{recruiter_profile.recruiter.id}"
                    )
                    cache.delete(
                        f"admin_recruiter_profile_{recruiter_profile.recruiter.id}"
                    )

                return APIResponse.success(
                    message=_("Recruiter role successfully updated")
                )

            return APIResponse.validation_error(
                field_errors=serializer.errors,
                message=_("Invalid data"),
            )

        except RecruiterProfile.DoesNotExist:
            return APIResponse.not_found(message=_("Recruiter not found"))

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                f"Error updating recruiter level: {str(e)}", exc_info=True
            )
            return APIResponse.server_error(
                message=_("An unexpected error occurred")
            )

    @extend_schema(
        summary="Get recruiter information",
        description="Retrieve recruiter profile details by recruiter ID.",
        parameters=[
            OpenApiParameter(
                name="recruiter_id",
                type=int,
                location=OpenApiParameter.PATH,
                description="ID of the recruiter to retrieve",
            )
        ],
        responses={
            200: OpenApiResponse(
                description="Recruiter information retrieved successfully",
                response={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": True},
                        "data": {
                            "type": "object",
                            "properties": {
                                "recruiter_id": {
                                    "type": "string",
                                    "example": "123e4567-e89b-12d3-a456-426614174000",
                                },
                                "full_name": {"type": "string", "example": "John Doe"},
                                "phone": {"type": "string", "example": "+998901234567"},
                                "level": {"type": "string", "example": "Admin"},
                                "is_admin": {"type": "boolean", "example": True},
                                "email": {
                                    "type": "string",
                                    "example": "john.doe@example.com",
                                },
                                "photo": {
                                    "type": "string",
                                    "example": "https://example.com/photo.jpg",
                                },
                            },
                        },
                    },
                },
            ),
            404: OpenApiResponse(
                description="Recruiter not found",
                response={
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean", "example": False},
                        "message": {"type": "string", "example": "Recruiter not found"},
                    },
                },
            ),
        },
        examples=[
            OpenApiExample(
                "Successful response",
                value={
                    "success": True,
                    "data": {
                        "recruiter_id": "123e4567-e89b-12d3-a456-426614174000",
                        "full_name": "John",
                        "phone": "+998901234567",
                        "level": "Admin",
                        "is_admin": True,
                        "email": "john.doe@example.com",
                        "photo": "https://example.com/photo.jpg",
                    },
                },
                response_only=True,
            )
        ],
    )
    def get(self, request, recruiter_id):
        """
        Get recruiter information
        Optimized with select_related
        """
        try:
            # Scope to admin's own company
            company_id = getattr(request.user, "company_id", None)
            if company_id is None:
                recruiter = Recruiter.objects.only("company_id").filter(pk=request.user.id).first()
                if recruiter is None:
                    return APIResponse.not_found(message=_("Admin recruiter not found"))
                company_id = recruiter.company_id

            recruiter_profile = get_object_or_404(
                RecruiterProfile.objects.select_related("recruiter"),
                id=recruiter_id,
                recruiter__company_id=company_id,
            )

            return APIResponse.success(
                data={
                    "recruiter_id": str(recruiter_profile.id),
                    "full_name": recruiter_profile.full_name,
                    "phone": recruiter_profile.phone,
                    "level": recruiter_profile.level,
                    "is_admin": recruiter_profile.is_admin,
                    "email": getattr(recruiter_profile.recruiter, "email", None),
                    "photo": (
                        recruiter_profile.photo.url
                        if recruiter_profile.photo
                        else None
                    ),
                },
                message=_("Recruiter information retrieved successfully"),
            )

        except RecruiterProfile.DoesNotExist:
            return APIResponse.not_found(message=_("Recruiter not found"))


recruiter_profile_list_view = RecruiterProfileListView.as_view()
recruiter_level_update_view = RecruiterLevelUpdateView.as_view()
