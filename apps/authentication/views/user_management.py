from rest_framework import generics, serializers, status
from rest_framework.views import APIView
from django.utils.translation import gettext as _
from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)

from core.responses import APIResponse

from ..models import CustomUser
from ..serializers import AccountDeleteSerializer, UserSerializer
from ..services.account_deletion import AccountDeletionService

from utils import IsCandidatePermission, IsSelfPermission


class UserDeleteView(generics.DestroyAPIView):
    """
    View for deleting a user — only the user themself can delete their account.
    """

    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsSelfPermission]
    lookup_field = "id"


class AccountDeleteView(APIView):
    """
    Self-service account deletion for candidates.

    Candidates can permanently delete their own account and all associated
    data. The deletion is immediate and irreversible; only consent records are
    retained (flagged as belonging to a deleted user) as required legal proof.
    Recruiters and staff are not allowed to self-delete — their accounts are
    tied to a company and must be removed by an administrator.
    """

    permission_classes = [IsCandidatePermission]
    serializer_class = AccountDeleteSerializer

    @extend_schema(
        summary="Delete my account (candidates only)",
        description=(
            "Permanently deletes the authenticated candidate's account and all "
            "associated data (profile, resumes, applications, saved vacancies, "
            "sessions). Requires the current password when the account has one — "
            "accounts created via Google or phone OTP only need `confirm: true`. "
            "On success the auth cookies are cleared and every session is revoked."
        ),
        request=AccountDeleteSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "AccountDeleteSuccessResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "message": serializers.CharField(),
                        "timestamp": serializers.DateTimeField(),
                    },
                ),
                description="Account deleted successfully",
                examples=[
                    OpenApiExample(
                        "Deleted",
                        value={
                            "success": True,
                            "message": "Your account has been permanently deleted",
                            "timestamp": "2026-07-27T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Missing confirmation or incorrect password",
                examples=[
                    OpenApiExample(
                        "Incorrect Password",
                        value={
                            "success": False,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Incorrect password.",
                            },
                            "timestamp": "2026-07-27T10:00:00+00:00",
                        },
                        status_codes=["400"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Only candidates can delete their own account",
            ),
        },
    )
    def delete(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        AccountDeletionService.delete_account(
            request.user,
            refresh_token=request.COOKIES.get("refresh_token"),
            reason=serializer.validated_data.get("reason", ""),
        )

        response = APIResponse.success(
            message=_("Your account has been permanently deleted"),
            status_code=status.HTTP_200_OK,
        )

        # Clear auth cookies (parameters must match those used when setting them)
        response.delete_cookie("access_token", path="/", samesite="None")
        response.delete_cookie("refresh_token", path="/", samesite="None")

        return response


user_delete_view = UserDeleteView.as_view()
account_delete_view = AccountDeleteView.as_view()
