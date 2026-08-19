"""
Vault service integration views.

Provides the API endpoint for candidates to register their LMS credentials
with the Vault service for grade synchronization.
"""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from django.utils.translation import gettext as _

from core.responses import APIResponse
from utils.candidate_permission import IsCandidatePermission

from apps.authentication.models import Candidate
from apps.edupartners.serializers.vault import VaultRegistrationSerializer
from apps.edupartners.services.vault import (
    register_student_in_vault,
    get_universities_from_vault,
    VaultInvalidCredentialsError,
    VaultAlreadyRegisteredError,
    VaultBadRequestError,
    VaultServiceError,
)
from apps.authentication.transitions import update_candidate_step, VERIFY_VAULT

logger = logging.getLogger(__name__)


class VaultRegistrationView(APIView):
    """
    POST — Register the authenticated candidate's LMS credentials with the Vault service.

    Requires:
    - Candidate must be authenticated (IsCandidatePermission)
    - Candidate must have an associated edupartner (university)

    Request body:
    - lms_login: LMS username
    - lms_password: LMS password

    The candidate's ID and edupartner ID are derived from the authenticated user.
    On successful registration (sync_status: "success"), the candidate's
    is_vault_verified field is set to True.
    """

    permission_classes = [IsCandidatePermission]

    def post(self, request, *args, **kwargs):
        serializer = VaultRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Get the candidate from the authenticated user
        # This ensures only the authenticated candidate can submit their own credentials
        # The student_id is derived from request.user.id, not from request body
        try:
            candidate = Candidate.objects.select_related("edupartner").get(
                id=request.user.id
            )
        except Candidate.DoesNotExist:
            return APIResponse.error(
                message=_("Candidate not found"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Ensure candidate has an associated edupartner
        if not candidate.edupartner_id:
            return APIResponse.error(
                message=_("You must have an associated educational partner (university) to register with LMS."),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Check if already vault verified
        if candidate.is_vault_verified:
            return APIResponse.error(
                message=_("You are already verified through LMS."),
                status_code=status.HTTP_409_CONFLICT,
            )

        try:
            result = register_student_in_vault(
                student_id=str(candidate.id),
                main_plat_id=str(candidate.edupartner_id),
                lms_login=serializer.validated_data["lms_login"],
                lms_password=serializer.validated_data["lms_password"],
            )
        except VaultInvalidCredentialsError as e:
            return APIResponse.error(
                message=_(str(e.message)),
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        except VaultAlreadyRegisteredError as e:
            # Student already registered in Vault — mark verified so they're not stuck.
            candidate.is_vault_verified = True
            candidate.save(update_fields=["is_vault_verified"])
            update_candidate_step(candidate, VERIFY_VAULT)
            return APIResponse.success(
                data={"sync_status": "success", "message": str(e.message)},
                message=_("Already verified through LMS."),
                status_code=status.HTTP_200_OK,
            )
        except VaultBadRequestError as e:
            return APIResponse.error(
                message=_(str(e.message)),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        except VaultServiceError as e:
            return APIResponse.error(
                message=_(str(e.message)),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        # Update candidate verification status based on sync result
        sync_status = result.get("sync_status", "pending")
        if sync_status == "success":
            candidate.is_vault_verified = True
            candidate.save(update_fields=["is_vault_verified"])
            update_candidate_step(candidate, VERIFY_VAULT)
        return APIResponse.success(
            data=result,
            message=_(result.get("message", "Registration successful")),
            status_code=status.HTTP_200_OK,
        )


class VaultUniversityListView(APIView):
    """
    GET — Retrieve the list of supported universities from the Vault service.

    This endpoint fetches universities directly from the Vault service
    and returns them under the 'data' key.

    No authentication required — public endpoint for registration flow.
    """

    permission_classes = [AllowAny]  # Public endpoint

    def get(self, request, *args, **kwargs):
        try:
            universities = get_universities_from_vault()
        except VaultServiceError as e:
            return APIResponse.error(
                message=_(str(e.message)),
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        return APIResponse.success(
            data=universities,
            message=_("Universities retrieved successfully"),
            status_code=status.HTTP_200_OK,
        )


vault_registration_view = VaultRegistrationView.as_view()
vault_university_list_view = VaultUniversityListView.as_view()
