
import logging
from rest_framework.views import APIView
from core.responses import APIResponse
from utils import IsAdminRecruiter
from utils.company_permission import IsCompanyApproved
from utils.view_mixins import RecruiterMixin
from ..serializers.recruiter import AdminRecruiterRegistrationSerializer
from apps.authentication.models import Recruiter
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class RegisterRecruiterAdminAPIView(RecruiterMixin, APIView):
    """
    API for admin-only recruiter registration and update.
    
    This endpoint allows admin recruiters to:
    - Create new recruiters with profiles (POST)
    - Update existing recruiters and profiles (PUT/PATCH)
    
    Only accessible by recruiters with admin level permission.
    Creates both Recruiter account and RecruiterProfile in a single request.
    """

    permission_classes = [IsAdminRecruiter, IsCompanyApproved]

    def post(self, request, *args, **kwargs):
        """
        Register a new recruiter.
        
        Required fields:
        - email: Recruiter's email address
        - password: Using django's set_password
        - company: UUID of the company
        - full_name: Full name of the recruiter
        
        Optional fields:
        - phone_number: Contact phone number
        - photo: Profile photo (image file)
        - level: Access level (Recruiter, Manager, Admin)
        """
        # Get admin's company to use as default if not provided
        admin_recruiter = self.get_recruiter()

        # Make mutable copy of request data
        data = request.data.copy()

        # Map 'role' to 'level' for backward compatibility
        if 'role' in data and 'level' not in data:
            data['level'] = data['role']

        # If company not provided, use admin's company
        if 'company' not in data and admin_recruiter.company:
            data['company'] = str(admin_recruiter.company.id)

        serializer = AdminRecruiterRegistrationSerializer(data=data)

        if not serializer.is_valid():
            return APIResponse.validation_error(
                field_errors=serializer.errors,
                message=_("Validation failed"),
            )

        try:
            recruiter = serializer.save()
            return APIResponse.created(
                data=serializer.to_representation(recruiter),
                message=_("Recruiter registered successfully"),
            )
        except Exception as e:
            logger.error(f"Failed to register recruiter: {e}", exc_info=True)
            return APIResponse.server_error(
                message=_("Failed to register recruiter"),
            )

    def put(self, request, recruiter_id=None, *args, **kwargs):
        """
        Update an existing recruiter.
        
        All fields are optional for update:
        - email: New email address
        - full_name: Updated full name
        - phone_number: Updated phone number
        - photo: Updated profile photo
        - level: Updated access level
        - password: New password (will use set_password)
        """
        return self._update_recruiter(request, recruiter_id, partial=False)

    def patch(self, request, recruiter_id=None, *args, **kwargs):
        """Partial update of recruiter. Same as PUT but allows partial data."""
        return self._update_recruiter(request, recruiter_id, partial=True)

    def _update_recruiter(self, request, recruiter_id, partial=True):
        """Internal method to handle recruiter updates."""
        if not recruiter_id:
            return APIResponse.bad_request(
                message=_("Recruiter ID is required for update")
            )

        # Get admin's company to verify they can update this recruiter
        admin_recruiter = self.get_recruiter()

        try:
            # Admin can only update recruiters in their company
            recruiter = Recruiter.objects.select_related('company').get(
                id=recruiter_id,
                company=admin_recruiter.company
            )
        except Recruiter.DoesNotExist:
            return APIResponse.not_found(
                message=_("Recruiter not found or not in your company")
            )

        serializer = AdminRecruiterRegistrationSerializer(
            data=request.data,
            context={'instance': recruiter},
            partial=partial
        )

        if not serializer.is_valid():
            return APIResponse.validation_error(
                field_errors=serializer.errors,
                message=_("Validation failed"),
            )

        try:
            updated_recruiter = serializer.update(recruiter, serializer.validated_data)
            return APIResponse.success(
                data=serializer.to_representation(updated_recruiter),
                message=_("Recruiter updated successfully"),
            )
        except Exception as e:
            logger.error(f"Failed to update recruiter: {e}", exc_info=True)
            return APIResponse.server_error(
                message=_("Failed to update recruiter"),
            )


register_recruiter_admin_view = RegisterRecruiterAdminAPIView.as_view()
