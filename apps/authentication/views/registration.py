import uuid
import logging

from rest_framework.views import APIView
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.exceptions import ValidationError

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample, inline_serializer

from ..models import CustomUser, Candidate, Recruiter
from ..serializers import (
    RegisterGeneralUserSerializer,
    CandidateSerializer,
    RecruiterSerializer,
)

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator as token_generator
from utils import encode_uid

from apps.general.services.email_service import send_email_from_template_type
from core.responses import APIResponse
from utils import IsAdminRecruiter
from utils.company_permission import IsCompanyApproved
from utils.view_mixins import RecruiterMixin
from utils.language import get_request_language
from django.utils.translation import gettext as _
from django.core.cache import cache

logger = logging.getLogger(__name__)


# Views for registering general user, candidate, recruiter
class GeneralUserRegisterView(generics.CreateAPIView):
    """
    View to register a general user. Only accessible by admin users."""

    queryset = CustomUser.objects.all()
    serializer_class = RegisterGeneralUserSerializer
    permission_classes = [IsAdminUser]


@extend_schema_view(
    post=extend_schema(
        summary="Register a candidate",
        description="Create a new candidate user account. Accepts email, date_of_birth, and consent agreement. "
                    "Sends a password-setup link to the provided email address. "
                    "If the email already exists (no password set), resends the setup email (up to 5 times/day). "
                    "Tokens are NOT returned in the response — the user must set a password via the email link.",
        request=CandidateSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    "CandidateRegisterResponse",
                    fields={
                        "email": serializers.EmailField(),
                    },
                ),
                description="Candidate registered successfully. Email sent for password setup.",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {"email": "candidate@example.com"},
                            "message": "Candidate registered successfully. Please check your email to set your password.",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["201"],
                    ),
                ],
            ),
            400: OpenApiResponse(
                response=inline_serializer(
                    "ValidationErrorResponse",
                    fields={
                        "success": serializers.BooleanField(default=False),
                        "error": inline_serializer(
                            "RegisterErrorDetail",
                            fields={
                                "code": serializers.CharField(default="VALIDATION_ERROR"),
                                "message": serializers.CharField(default="Input validation failed"),
                                "field_errors": serializers.DictField(child=serializers.ListField(child=serializers.CharField()), default={}),
                            },
                        ),
                        "timestamp": serializers.DateTimeField(),
                    },
                ),
                description="Validation error — missing fields, invalid email, or consented not agreed",
            ),
            429: OpenApiResponse(description="Too many requests — daily resend limit reached"),
        },
    ),
)
class CandidateRegisterView(generics.CreateAPIView):
    """
    View to register a candidate with consent tracking.
    Sends a set-password email link instead of accepting password at registration.
    """

    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Create a new candidate user with consent tracking.
        Sends a password setup link to the candidate's email.
        """
        email = request.data.get("email")

        # If user already exists:
        # - when password is already set, return "already exists"
        # - when candidate has no password yet, allow resending set-password email up to 5 times/day
        if email:
            existing_user = CustomUser.objects.filter(email=email).first()
            if existing_user:
                if existing_user.has_usable_password() and existing_user.password:
                    return APIResponse.validation_error(
                        message=_("Input validation failed"),
                        field_errors={"email": [_("User with this email already exists.")]},
                    )

                if not existing_user.is_candidate:
                    return APIResponse.validation_error(
                        message=_("Input validation failed"),
                        field_errors={"email": [_("User with this email already exists.")]},
                    )

                candidate = Candidate.objects.filter(pk=existing_user.pk).first()
                if not candidate:
                    return APIResponse.validation_error(
                        message=_("Input validation failed"),
                        field_errors={"email": [_("User with this email already exists.")]},
                    )

                cache_key = f"candidate_reg_email_count_{email}"
                count = cache.get(cache_key, 0)

                if count >= 5:
                    return APIResponse.validation_error(
                        message=_("Input validation failed"),
                        field_errors={"email": [_("User with this email already exists.")]},
                    )

                cache.set(cache_key, count + 1, timeout=86400)  # 24 hours
                self._send_set_password_email(candidate, request)

                return APIResponse.created(
                    data={"email": email},
                    message=_("Candidate registered successfully. Please check your email to set your password."),
                )

        serializer = self.get_serializer(
            data=request.data,
            context={'request': request}
        )

        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            return APIResponse.validation_error(
                message=_("Input validation failed"),
                field_errors=serializer.errors,
            )

        self.perform_create(serializer)

        # Send set-password email immediately via RQ
        candidate = Candidate.objects.get(email=serializer.data["email"])
        self._send_set_password_email(candidate, request)

        return APIResponse.created(
            data={"email": serializer.data["email"]},
            message=_("Candidate registered successfully. Please check your email to set your password."),
        )

    def _send_set_password_email(self, candidate, request):
        """
        Send a password setup email to the newly registered candidate.
        Uses RQ for async processing with no delay.
        """
        try:
            uid = encode_uid(candidate.pk)
            token = token_generator.make_token(candidate)

            set_password_url = f"{settings.FRONTEND_URL}/set-password/candidate/{uid}/{token}/"

            language = get_request_language()

            context = {
                "user_email": candidate.email,
                "set_password_url": set_password_url,
                "site_name": getattr(settings, "SITE_NAME", "WorkXplorer"),
            }

            send_email_from_template_type(
                to_email=candidate.email,
                template_type="set-password",
                context=context,
                language=language,
                delay_seconds=0,
            )

            logger.info(f"Set-password email queued for candidate {candidate.id}")
        except Exception as e:
            logger.error(
                f"Failed to queue set-password email for candidate {candidate.id}: {e}",
                exc_info=True,
            )


class RecruiterRegisterView(generics.CreateAPIView):
    """
    View to register a recruiter. Accessible by anyone.
    """

    queryset = Recruiter.objects.all()
    serializer_class = RecruiterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Create a new recruiter user with consent tracking.
        """
        serializer = self.get_serializer(
            data=request.data,
            context={'request': request}
        )

        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            message = _("Input validation failed")
            if "email" in serializer.errors:
                message = str(serializer.errors["email"][0])
            return APIResponse.validation_error(
                message=message,
                field_errors=serializer.errors,
            )

        self.perform_create(serializer)
        return APIResponse.created(
            data={"email": serializer.data["email"]},
            message=_("Recruiter registered successfully"),
        )


class RecruiterApprovalView(RecruiterMixin, APIView):
    """
    Bulk approve recruiters by UUID IDs. Only accessible by company admin recruiters.
    Admins can only view and approve recruiters registering for their own company.
    Uses RecruiterMixin for efficient recruiter/company retrieval with caching.

    GET allows unapproved companies (returns demo data).
    POST requires IsCompanyApproved (via get_permissions).
    """

    permission_classes = [IsAdminRecruiter]

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(IsCompanyApproved())
        return permissions

    def _get_admin_company(self):
        try:
            recruiter = self.get_recruiter()
            return recruiter.company
        except Exception:
            return None

    def get(self, request, *args, **kwargs):
        """
        List all recruiters waiting for approval for the admin's company.
        Only shows recruiters belonging to the authenticated admin's company.
        Supports filtering by full_name via query parameter.
        """
        company = self._get_admin_company()
        if not company:
            return APIResponse.bad_request(
                message=_("Admin has no associated company."),
            )

        if not company.is_active:
            from apps.vacancies.services.demo_data import DEMO_WAITING_RECRUITERS
            return APIResponse.success(
                data=DEMO_WAITING_RECRUITERS,
                message=_("Recruiters retrieved successfully"),
            )

        recruiters = Recruiter.objects.filter(
            is_waiting_approval=True,
            company=company
        ).select_related("company")

        # Filter by full_name if provided (searches in related RecruiterProfile)
        full_name = request.query_params.get("full_name")
        if full_name:
            recruiters = recruiters.filter(recruiterprofile__full_name__icontains=full_name)

        serializer = RecruiterSerializer(recruiters, many=True)
        return APIResponse.success(data=serializer.data, message=_("Recruiters retrieved successfully"))

    def post(self, request, *args, **kwargs):
        """
        Approve multiple recruiters for the admin's company.
        Only recruiters belonging to the admin's company can be approved.
        
        Example body:
        {
            "ids": ["id1", "id2"],
            "approve": true
        }
        """
        company = self._get_admin_company()
        if not company:
            return APIResponse.bad_request(
                message=_("Admin has no associated company."),
            )

        recruiter_ids = request.data.get("ids", [])
        approve = request.data.get("approve", True)

        # Validate input is a list of UUIDs
        if not recruiter_ids or not isinstance(recruiter_ids, list):
            return APIResponse.validation_error(
                message=_("A list of recruiter UUIDs is required."),
            )

        # Validate approve is a boolean
        if not isinstance(approve, bool):
            return APIResponse.validation_error(
                message=_("approve must be a boolean value."),
            )

        # This API is for approval only
        if not approve:
            return APIResponse.bad_request(
                message=_("This API is for approval only. Use rejection API for rejections."),
            )

        valid_ids = []
        invalid_ids = []

        # Validate each ID is a UUID
        for rid in recruiter_ids:
            try:
                valid_ids.append(uuid.UUID(str(rid)))
            except ValueError:
                invalid_ids.append(rid)

        # If there are invalid UUIDs, return error
        if invalid_ids:
            return APIResponse.validation_error(
                message=_("Some IDs are not valid UUIDs."),
                details={"invalid_ids": invalid_ids},
            )

        # Fetch recruiters to approve - only from admin's company
        recruiters = list(
            Recruiter.objects.filter(
                id__in=valid_ids,
                is_waiting_approval=True,
                company=company
            ).prefetch_related("recruiterprofile_set")
        )

        # If no recruiters found, return error
        if not recruiters:
            return APIResponse.not_found(
                message=_("No recruiters found to approve."),
            )

        return self._approve_recruiters(recruiters)

    def _approve_recruiters(self, recruiters):
        """
        Handle the approval flow for recruiters.
        Updates their status and sends confirmation emails.
        """
        # Bulk update
        updated_count = Recruiter.objects.filter(
            id__in=[r.id for r in recruiters]
        ).update(is_waiting_approval=False)

        # Send confirmation emails to approved recruiters
        for recruiter in recruiters:
            try:
                token = token_generator.make_token(recruiter)
                uid = encode_uid(recruiter.pk)

                # Build set-password URL (frontend link)
                reset_url = f"{settings.FRONTEND_URL}/set-password/recruiter/{uid}/{token}/"

                # Get full name from recruiter profile if available
                profile = recruiter.recruiterprofile_set.first()
                full_name = profile.full_name if profile else ""

                # Prepare context for email template
                context = {
                    "user_email": recruiter.email,
                    "user_full_name": full_name,
                    "reset_url": reset_url,
                    "site_name": getattr(settings, "SITE_NAME", "Our Site"),
                }

                # Send confirmation email
                logger.info(f"Confirmation email queued for recruiter {recruiter.id}")
                send_email_from_template_type(
                    to_email=recruiter.email,
                    template_type="confirm-recruiter",
                    context=context,
                    language="uz",
                )

            except Exception as e:
                logger.error(
                    f"Failed to queue email for recruiter {recruiter.id}: {e}",
                    exc_info=True,
                )

        return APIResponse.success(
            data={"approved_count": updated_count},
            message=_("%(count)s recruiter(s) approved successfully.") % {"count": updated_count},
        )


class RecruiterRejectionView(RecruiterMixin, APIView):
    """
    Bulk reject recruiters by UUID IDs. Only accessible by company admin recruiters.
    Admins can only reject recruiters registering for their own company.
    Uses RecruiterMixin for efficient recruiter/company retrieval with caching.
    """

    permission_classes = [IsAdminRecruiter, IsCompanyApproved]

    def _get_admin_company(self):
        """
        Get the company of the authenticated admin recruiter.
        Uses RecruiterMixin's get_recruiter() which includes caching and select_related.
        Returns the company or None if not found.
        """
        try:
            recruiter = self.get_recruiter()
            return recruiter.company
        except Exception:
            return None

    def post(self, request, *args, **kwargs):
        """
        Reject multiple recruiters for the admin's company.
        Only recruiters belonging to the admin's company can be rejected.
        
        Example body:
        {
            "ids": ["id1", "id2"],
            "approve": false
        }
        """
        company = self._get_admin_company()
        if not company:
            return APIResponse.bad_request(
                message=_("Admin has no associated company."),
            )

        recruiter_ids = request.data.get("ids", [])
        approve = request.data.get("approve", False)

        # Validate input is a list of UUIDs
        if not recruiter_ids or not isinstance(recruiter_ids, list):
            return APIResponse.validation_error(
                message=_("A list of recruiter UUIDs is required."),
            )

        # Validate approve is a boolean
        if not isinstance(approve, bool):
            return APIResponse.validation_error(
                message=_("approve must be a boolean value."),
            )

        # This API is for rejection only
        if approve:
            return APIResponse.bad_request(
                message=_("This API is for rejection only. Use approval API for approvals."),
            )

        valid_ids = []
        invalid_ids = []

        # Validate each ID is a UUID
        for rid in recruiter_ids:
            try:
                valid_ids.append(uuid.UUID(str(rid)))
            except ValueError:
                invalid_ids.append(rid)

        # If there are invalid UUIDs, return error
        if invalid_ids:
            return APIResponse.validation_error(
                message=_("Some IDs are not valid UUIDs."),
                details={"invalid_ids": invalid_ids},
            )

        # Fetch recruiters to reject - only from admin's company
        recruiters = list(
            Recruiter.objects.filter(
                id__in=valid_ids,
                is_waiting_approval=True,
                company=company
            ).prefetch_related("recruiterprofile_set")
        )

        # If no recruiters found, return error
        if not recruiters:
            return APIResponse.not_found(
                message=_("No recruiters found to reject."),
            )

        return self._reject_recruiters(recruiters)

    def _reject_recruiters(self, recruiters):
        """
        Handle the rejection flow for recruiters.
        Sends rejection emails and deletes recruiter profiles.
        """
        rejected_count = 0
        rejected_emails = []

        for recruiter in recruiters:
            try:
                # Get full name from recruiter profile if available
                profile = recruiter.recruiterprofile_set.first()
                full_name = profile.full_name if profile else ""
                recruiter_email = recruiter.email

                # Prepare context for rejection email template
                context = {
                    "user_email": recruiter_email,
                    "user_full_name": full_name,
                    "site_name": getattr(settings, "SITE_NAME", "Our Site"),
                }

                # Send rejection email
                logger.info(f"Rejection email queued for recruiter {recruiter.id}")
                send_email_from_template_type(
                    to_email=recruiter_email,
                    template_type="rejected-recruiter",
                    context=context,
                    language="uz",
                )

                # Delete the recruiter profile first (if exists)
                if profile:
                    profile.delete()
                    logger.info(f"RecruiterProfile deleted for recruiter {recruiter.id}")

                # Delete the recruiter
                recruiter.delete()
                logger.info(f"Recruiter {recruiter.id} deleted successfully")

                rejected_count += 1
                rejected_emails.append(recruiter_email)

            except Exception as e:
                logger.error(
                    f"Failed to process rejection for recruiter {recruiter.id}: {e}",
                    exc_info=True,
                )

        return APIResponse.success(
            data={
                "rejected_count": rejected_count,
                "rejected_emails": rejected_emails,
            },
            message=_("%(count)s recruiter(s) rejected successfully.") % {"count": rejected_count},
        )


general_user_register_view = GeneralUserRegisterView.as_view()
candidate_register_view = CandidateRegisterView.as_view()
recruiter_register_view = RecruiterRegisterView.as_view()
recruiter_approval_view = RecruiterApprovalView.as_view()
recruiter_rejection_view = RecruiterRejectionView.as_view()
