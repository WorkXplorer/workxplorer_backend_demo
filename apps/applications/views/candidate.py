import logging
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample, inline_serializer

from ..models import JobApplication, ApplicationStatus, ApplicationDocument, ApplicationStatusModel, StatusCategory
from apps.vacancies.models import Vacancy, VacancySkill
from apps.authentication.models import Candidate
from apps.conversations.services import create_status_change_message
from apps.notifications.services import ApplicationNotificationService
from ..serializers import (
    JobApplicationCreateSerializer,
    JobApplicationDetailSerializer,
    JobApplicationListSerializer,
)
from utils.view_mixins import CandidateMixin
from django.db.models import Prefetch
from core.responses import APIResponse
from django.utils.translation import gettext as _
from apps.authentication.transitions import update_candidate_step, VACANCY_APPLY
from utils.candidate_permission import IsCandidatePermission

logger = logging.getLogger(__name__)


@extend_schema_view(
    post=extend_schema(
        summary="Apply to vacancy",
        description="Submit a job application to a specific vacancy. "
                    "Candidates can include a resume, cover letter, portfolio URL, "
                    "earliest start date, and supporting documents.",
        request=inline_serializer(
            "ApplyToVacancyRequest",
            fields={
                "vacancy_id": serializers.UUIDField(help_text="UUID of the vacancy to apply to"),
                "resume_id": serializers.UUIDField(required=False, help_text="UUID of the resume to use"),
                "cover_letter": serializers.CharField(required=False, help_text="Cover letter text"),
                "portfolio_url": serializers.URLField(required=False, help_text="Portfolio URL"),
                "earliest_start_date": serializers.DateField(required=False, help_text="Earliest start date (YYYY-MM-DD)"),
                "documents_data": serializers.ListField(
                    child=serializers.FileField(),
                    required=False,
                    help_text="List of document files to attach to the application",
                ),
            },
        ),
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    "ApplyToVacancyResponse",
                    fields={
                        "id": serializers.UUIDField(),
                        "applied_at": serializers.DateTimeField(),
                        "updated_at": serializers.DateTimeField(),
                        "candidate": inline_serializer(
                            "CandidateBrief",
                            fields={
                                "id": serializers.UUIDField(),
                                "email": serializers.EmailField(),
                                "first_name": serializers.CharField(),
                                "last_name": serializers.CharField(),
                            },
                        ),
                        "vacancy": inline_serializer(
                            "VacancyBrief",
                            fields={
                                "id": serializers.UUIDField(),
                                "title": serializers.CharField(),
                                "company": inline_serializer(
                                    "CompanyBrief",
                                    fields={"id": serializers.UUIDField(), "name": serializers.CharField()},
                                ),
                                "employment_type": serializers.CharField(),
                                "employment_format": serializers.CharField(),
                            },
                        ),
                        "status": serializers.CharField(),
                        "status_display": serializers.CharField(),
                        "days_since_application": serializers.IntegerField(),
                        "is_recent": serializers.BooleanField(),
                        "can_withdraw": serializers.BooleanField(),
                        "cover_letter": serializers.CharField(allow_null=True),
                        "portfolio_url": serializers.URLField(allow_null=True),
                        "earliest_start_date": serializers.DateField(allow_null=True),
                        "documents": serializers.ListField(
                            child=inline_serializer(
                                "DocumentBrief",
                                fields={"id": serializers.UUIDField(), "title": serializers.CharField(), "created_at": serializers.DateTimeField()},
                            ),
                        ),
                        "resume_used": inline_serializer(
                            "ResumeUsed",
                            fields={"id": serializers.UUIDField(), "title": serializers.CharField()},
                        ),
                    },
                ),
                description="Application submitted successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "applied_at": "2026-06-30T10:00:00Z",
                                "updated_at": "2026-06-30T10:00:00Z",
                                "candidate": {
                                    "id": "550e8400-e29b-41d4-a716-446655440001",
                                    "email": "candidate@example.com",
                                    "first_name": "John",
                                    "last_name": "Doe",
                                },
                                "vacancy": {
                                    "id": "550e8400-e29b-41d4-a716-446655440002",
                                    "title": "Software Engineer",
                                    "company": {"id": "550e8400-e29b-41d4-a716-446655440003", "name": "Tech Corp"},
                                    "employment_type": "FULL_TIME",
                                    "employment_format": "OFFICE",
                                },
                                "status": "APPLIED",
                                "status_display": "Applied",
                                "days_since_application": 0,
                                "is_recent": True,
                                "can_withdraw": True,
                                "cover_letter": "I'm excited to apply...",
                                "portfolio_url": None,
                                "earliest_start_date": None,
                                "documents": [],
                                "resume_used": {"id": "550e8400-e29b-41d4-a716-446655440004", "title": "My Resume"},
                            },
                            "message": "Application submitted successfully",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["201"],
                    ),
                ],
            ),
            400: OpenApiResponse(description="Validation error, inactive vacancy, or duplicate application"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
        },
    ),
)
class ApplyToVacancyView(generics.CreateAPIView):
    """
    Allows a candidate to apply to a specific vacancy.
    Optimized to minimize database queries.
    """

    serializer_class = JobApplicationCreateSerializer
    permission_classes = [IsAuthenticated, IsCandidatePermission]

    def create(self, request, *args, **kwargs):
        """Enhanced create method with optimized DB queries"""
        try:
            # Reuse the candidate relation already resolved by the permission class.
            try:
                candidate = Candidate.objects.select_related("candidateprofile").get(
                    pk=request.user.pk
                )
            except Candidate.DoesNotExist:
                return APIResponse.bad_request(
                    message=_("Candidate profile not found"),
                    details=_("No candidate profile exists for this user")
                )

            vacancy_id = request.data.get("vacancy_id")
            if not vacancy_id:
                return APIResponse.validation_error(
                    message=_("Vacancy ID is required"),
                    field_errors={"vacancy_id": ["This field is required"]},
                )

            # Single query with select_related to get vacancy + company
            try:
                vacancy = Vacancy.objects.select_related("company", "created_by").get(
                    id=vacancy_id
                )
            except Vacancy.DoesNotExist:
                return APIResponse.validation_error(
                    message=_("Vacancy not found"),
                    field_errors={"vacancy_id": ["Invalid vacancy ID"]},
                )

            if not vacancy.is_active:
                return APIResponse.bad_request(
                    message=_("Vacancy is no longer active"),
                    details=_("This vacancy is no longer accepting applications")
                )

            # Add candidate and vacancy to serializer context
            serializer = self.get_serializer(
                data=request.data,
                context={
                    "request": request,
                    "candidate": candidate,
                    "vacancy": vacancy,
                },
            )

            # Validate and create application
            serializer.is_valid(raise_exception=True)

            # ponytail: TOCTOU race — UniqueConstraint catches duplicates at DB level,
            # catch IntegrityError instead of .exists() pre-check
            with transaction.atomic():
                try:
                    self.perform_create(serializer)
                except IntegrityError:
                    return APIResponse.bad_request(
                        message=_("Application already exists"),
                        details=_("You have already applied to this vacancy")
                    )
            update_candidate_step(candidate, VACANCY_APPLY)

            # Return created application data
            application = serializer.instance
            # ponytail: use model properties instead of recomputing
            days_since_application = application.days_since_application
            is_recent = application.is_recent

            # Reuse the ApplicationStatusModel fetched during serializer.create()
            # to avoid extra DB hits for status_display and can_withdraw.
            applied_status_model = getattr(serializer, "_applied_status_model", None)
            if applied_status_model:
                status_display = applied_status_model.label
                can_withdraw = not applied_status_model.category.is_terminal
            else:
                status_display = application.get_status_display()
                can_withdraw = application.can_be_withdrawn()

            response_data = {
                "id": str(application.id),
                "applied_at": application.applied_at,
                "updated_at": application.updated_at,
                "candidate": {
                    "id": str(candidate.id),
                    "email": candidate.email,
                    "first_name": getattr(candidate, "first_name", ""),
                    "last_name": getattr(candidate, "last_name", ""),
                },
                "vacancy": {
                    "id": str(vacancy.id),
                    "title": vacancy.title,
                    "company": {
                        "id": str(vacancy.company.id),
                        "name": vacancy.company.name,
                    },
                    "employment_type": vacancy.employment_type,
                    "employment_format": vacancy.employment_format,
                },
                "status": application.status,
                "status_display": status_display,
                "days_since_application": days_since_application,
                "is_recent": is_recent,
                "can_withdraw": can_withdraw,
                "cover_letter": application.cover_letter,
                "portfolio_url": application.portfolio_url,
                "earliest_start_date": application.earliest_start_date,

                "documents": [
                    {
                        "id": str(doc.id),
                        "title": doc.title,
                        "created_at": doc.created_at,
                    }
                    for doc in getattr(serializer, "created_documents", [])
                ],
                "resume_used": (
                    {
                        "id": str(serializer.resume.id),
                        "title": getattr(serializer.resume, "title", "Resume"),
                    }
                    if hasattr(serializer, "resume") and serializer.resume
                    else None
                ),
            }

            try:
                ApplicationNotificationService.notify_recruiter_new_application(
                    application
                )
            except Exception:
                logger.exception(
                    "Failed to notify recruiter about new application %s",
                    application.id,
                )

            return APIResponse.created(
                data=response_data, message=_("Application submitted successfully")
            )

        except ValidationError as e:
            # Return 400 for validation errors
            field_errors = {}
            if hasattr(e, 'detail'):
                if isinstance(e.detail, dict):
                    field_errors = e.detail
                elif isinstance(e.detail, list):
                    field_errors = {"detail": e.detail}
                else:
                    field_errors = {"detail": [str(e.detail)]}
            else:
                field_errors = {"detail": [str(e)]}

            return APIResponse.validation_error(
                message=_("Validation failed"),
                field_errors=field_errors
            )

        except Exception as e:
            # Log the actual error with full traceback for debugging
            logger.error(
                f"Unexpected error in ApplyToVacancyView: {e}",
                exc_info=True,
                extra={
                    'user_email': getattr(request.user, 'email', 'unknown'),
                    'vacancy_id': request.data.get('vacancy_id'),
                }
            )
            return APIResponse.server_error(
                message=_("Failed to submit application"),
                details=_("An unexpected error occurred while processing your application")
            )


@extend_schema_view(
    get=extend_schema(
        summary="List my applications",
        description="Get all job applications submitted by the authenticated candidate. "
                    "Includes vacancy details, company info, current status, and documents.",
        responses={
            200: OpenApiResponse(
                response=JobApplicationListSerializer(many=True),
                description="List of candidate's applications",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
)
class CandidateApplicationsListView(CandidateMixin, generics.ListAPIView):
    """
    Shows all applications submitted by the current candidate.

    Optimized to reduce duplicate queries and improve performance.
    """

    serializer_class = JobApplicationListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filter applications to only those submitted by the current candidate.

        Optimizations:
        - Cache the candidate lookup to avoid repeated DB hits from get_candidate()
        - Use select_related to pull multi-table parent (customuser) and related vacancy/company/resume in one query
        - Prefetch documents with ordering to avoid per-object document queries
        - Prefetch recruiter profiles to avoid N+1 queries on recruiter info
        """
        user = self.request.user

        if not getattr(user, "is_candidate", False):
            return JobApplication.objects.none()

        try:
            # Get candidate (cached by mixin on request object)
            # The mixin handles caching, so multiple calls won't trigger DB queries
            candidate = self.get_candidate()

            from apps.profiles.models import RecruiterProfile
            
            # Optimize query with select_related and prefetch_related
            return (
                JobApplication.objects.filter(candidate=candidate, is_demo=False)
                .select_related(
                    "vacancy",
                    "vacancy__company",
                    "vacancy__created_by",
                    "resume_used",
                )
                .prefetch_related(
                    Prefetch(
                        "documents",
                        queryset=ApplicationDocument.objects.only(
                            "id", "title", "created_at", "application_id"
                        ).order_by("-created_at"),
                    ),
                    Prefetch(
                        "vacancy__created_by__recruiterprofile_set",
                        queryset=RecruiterProfile.objects.only(
                            "id", "recruiter_id", "full_name"
                        ),
                        to_attr="prefetched_profiles",
                    ),
                )
                .order_by("-applied_at")
            )
        except Http404:
            return JobApplication.objects.none()


class CandidateApplicationActionMixin(CandidateMixin):
    """
    Shared helpers for candidate application actions.

    Consolidates repeated optimized application lookup and repeated
    status-change response flow.
    """

    def _get_candidate_application(self):
        application_id = self.kwargs.get("application_id")
        candidate = self.get_candidate()

        try:
            return (
                JobApplication.objects.select_related(
                    "vacancy", "vacancy__company", "resume_used"
                )
                .prefetch_related(
                    "documents",
                    Prefetch(
                        "vacancy__vacancyskill_set",
                        queryset=VacancySkill.objects.select_related("skill"),
                    ),
                    "resume_used__resume_skills__skill",
                )
                .get(id=application_id, candidate=candidate)
            )
        except JobApplication.DoesNotExist:
            raise Http404("Application not found")

    def _is_offer_response_status(self, application, new_status):
        """Check if the new status represents an offer accept or reject."""
        from apps.applications.models import ApplicationStatusModel, StatusCategory
        try:
            status_model = ApplicationStatusModel.objects.filter(
                company=application.vacancy.company,
                key=new_status,
                is_active=True,
            ).select_related('category').first()
            if status_model:
                return status_model.category.key in {StatusCategory.HIRED, StatusCategory.OFFER_REJECTED}
        except Exception:
            logger.exception(
                "Failed to determine offer response status for application %s and status %s",
                getattr(application, "id", None),
                new_status,
            )
        return False

    def _apply_status_change(
            self,
            request,
            *,
            application,
            new_status,
            success_message,
            failure_message,
            notes,
            candidate_message=None,
            set_earliest_start_date=False,
    ):
        old_status = application.status

        try:
            application.advance_status(
                new_status=new_status,
                user_type="candidate",
                notes=notes,
            )

            if set_earliest_start_date:
                application.earliest_start_date = timezone.now().date()
                application.save()

            create_status_change_message(
                application=application,
                old_status=old_status,
                new_status=new_status,
                recruiter_note=None,
                changed_by="CANDIDATE",
                candidate_message=candidate_message,
            )

            if new_status in {
                ApplicationStatus.OFFER_ACCEPTED,
                ApplicationStatus.OFFER_REJECTED,
            } or self._is_offer_response_status(application, new_status):
                try:
                    ApplicationNotificationService.notify_recruiter_offer_response(
                        application
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify recruiter about offer response for application %s",
                        application.id,
                    )

            serializer = self.get_serializer(application)
            return APIResponse.success(data=serializer.data, message=success_message)
        except ValidationError as e:
            return APIResponse.validation_error(
                message=failure_message,
                details=str(e),
            )


@extend_schema_view(
    put=extend_schema(
        summary="Withdraw application",
        description="Withdraw a submitted application. Only allowed if the application's current status "
                    "is not terminal (e.g., can withdraw from APPLIED or REVIEWED but not from HIRED or REJECTED).",
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Application withdrawn successfully",
            ),
            400: OpenApiResponse(description="Cannot withdraw application with current status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
    patch=extend_schema(
        summary="Withdraw application",
        description="Withdraw a submitted application. Only allowed if the application's current status "
                    "is not terminal.",
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Application withdrawn successfully",
            ),
            400: OpenApiResponse(description="Cannot withdraw application with current status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
)
class WithdrawApplicationView(CandidateApplicationActionMixin, generics.UpdateAPIView):
    """
    Allows candidates to withdraw their own applications.

    This gives candidates control over their application process.
    They might withdraw if they accept another offer or if they're
    no longer interested in the position.
    """

    permission_classes = [IsAuthenticated, IsCandidatePermission]
    serializer_class = JobApplicationDetailSerializer

    def get_object(self):
        """
        Get the application to withdraw with permission checking.
        Optimized with select_related and prefetch_related to minimize database queries.
        """
        application = self._get_candidate_application()

        # Check if withdrawal is allowed
        if not application.can_be_withdrawn():
            raise ValidationError(
                {
                    "detail": _(
                        "Cannot withdraw application with status: %(status_display)s"
                    )
                    % {"status_display": application.get_status_display()}
                }
            )

        return application

    def _get_company_withdrawn_key(self, application):
        """Resolve the WITHDRAWN-category status key for this company."""
        withdrawn_status = ApplicationStatusModel.objects.filter(
            company=application.vacancy.company,
            category__key=StatusCategory.WITHDRAWN,
            is_active=True,
        ).first()
        if withdrawn_status:
            return withdrawn_status.key
        return ApplicationStatus.WITHDRAWN

    def update(self, request, *args, **kwargs):
        """
        Perform the withdrawal by updating the status.
        """
        application = self.get_object()
        withdrawn_key = self._get_company_withdrawn_key(application)
        return self._apply_status_change(
            request,
            application=application,
            new_status=withdrawn_key,
            success_message=_("Application withdrawn successfully"),
            failure_message=_("Withdrawal failed"),
            notes="Application withdrawn by candidate",
        )


@extend_schema_view(
    put=extend_schema(
        summary="Reapply to vacancy",
        description="Reapply to a vacancy after a previous rejection or withdrawal. "
                    "Only allowed if the previous application status allows reapplication.",
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Reapplication successful",
            ),
            400: OpenApiResponse(description="Cannot reapply with current status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
    patch=extend_schema(
        summary="Reapply to vacancy",
        description="Reapply to a vacancy after a previous rejection or withdrawal.",
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Reapplication successful",
            ),
            400: OpenApiResponse(description="Cannot reapply with current status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
)
class ReapplyToVacancyView(CandidateApplicationActionMixin, generics.UpdateAPIView):
    """
    Perform reapplication by updating status to applied.
    This allows candidates to reapply to a vacancy they previously applied to,
    provided their previous application status allows it (e.g., rejected or withdrawn).
    """

    permission_classes = [IsAuthenticated, IsCandidatePermission]
    serializer_class = JobApplicationDetailSerializer

    def get_object(self):
        """
        Get the application to reapply with permission checking.
        Optimized with select_related and prefetch_related to minimize database queries.
        """
        application = self._get_candidate_application()

        # Check if reapplication is allowed
        if not application.can_be_reapplied():
            raise ValidationError(
                {
                    "detail": _(
                        "Cannot reapply to vacancy with status: %(status)s"
                    )
                    % {"status": application.get_status_display()}
                }
            )

        return application

    def update(self, request, *args, **kwargs):
        """
        Perform the reapplication by updating the status.
        """
        application = self.get_object()
        return self._apply_status_change(
            request,
            application=application,
            new_status=ApplicationStatus.APPLIED,
            success_message=_("Reapplication successful"),
            failure_message=_("Reapplication failed"),
            notes="Reapplied by candidate",
            set_earliest_start_date=True,
        )


@extend_schema_view(
    put=extend_schema(
        summary="Accept job offer",
        description="Accept a job offer. The application must be in OFFERED status. "
                    "Optionally accepts a 'cover_letter' field as a message to the recruiter.",
        request=inline_serializer(
            "AcceptOfferRequest",
            fields={
                "cover_letter": serializers.CharField(
                    required=False, default="",
                    help_text="Optional message to the recruiter",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Offer accepted successfully",
            ),
            400: OpenApiResponse(description="Application is not in OFFERED status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
    patch=extend_schema(
        summary="Accept job offer",
        description="Accept a job offer. The application must be in OFFERED status.",
        request=inline_serializer(
            "AcceptOfferRequest",
            fields={
                "cover_letter": serializers.CharField(
                    required=False, default="",
                    help_text="Optional message to the recruiter",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Offer accepted successfully",
            ),
            400: OpenApiResponse(description="Application is not in OFFERED status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
)
class AcceptOfferView(CandidateApplicationActionMixin, generics.UpdateAPIView):
    """
    Allows candidates to accept job offers.

    Sets the application status to the company's HIRED-category status
    (resolved from ApplicationStatusModel). Falls back to OFFER_ACCEPTED
    if the flexible system is not available.
    """

    permission_classes = [IsAuthenticated, IsCandidatePermission]
    serializer_class = JobApplicationDetailSerializer

    def _get_company_hired_key(self, application):
        """Resolve the HIRED-category status key for this company."""
        hired_status = ApplicationStatusModel.objects.filter(
            company=application.vacancy.company,
            category__key=StatusCategory.HIRED,
            is_active=True,
        ).first()
        if hired_status:
            return hired_status.key
        return ApplicationStatus.OFFER_ACCEPTED

    def get_object(self):
        """
        Get the application with offer to accept.
        Optimized with select_related and prefetch_related to minimize database queries.
        """
        application = self._get_candidate_application()

        # Check if current status is in the OFFERED category
        offered_key = self._get_company_offered_key(application)
        if application.status != offered_key:
            raise ValidationError(
                {
                    "detail": _(
                        "Can only accept applications with %(status)s status"
                    )
                    % {"status": "OFFERED"}
                }
            )

        return application

    def _get_company_offered_key(self, application):
        """Resolve the OFFERED-category status key for this company."""
        offered_status = ApplicationStatusModel.objects.filter(
            company=application.vacancy.company,
            category__key=StatusCategory.OFFERED,
            is_active=True,
        ).first()
        if offered_status:
            return offered_status.key
        return ApplicationStatus.OFFERED

    def update(self, request, *args, **kwargs):
        """
        Accept the offer by updating status to the HIRED-category key.
        Optionally accepts a cover_letter field as a message to the recruiter.
        """
        application = self.get_object()
        candidate_message = request.data.get("cover_letter", "").strip()
        hired_key = self._get_company_hired_key(application)
        return self._apply_status_change(
            request,
            application=application,
            new_status=hired_key,
            success_message=_("Offer accepted successfully"),
            failure_message=_("Failed to accept offer"),
            notes="Offer accepted by candidate",
            candidate_message=candidate_message or None,
        )


@extend_schema_view(
    put=extend_schema(
        summary="Reject job offer",
        description="Reject a job offer. The application must be in OFFERED status. "
                    "Optionally accepts a 'cover_letter' field as a message to the recruiter.",
        request=inline_serializer(
            "RejectOfferRequest",
            fields={
                "cover_letter": serializers.CharField(
                    required=False, default="",
                    help_text="Optional message to the recruiter",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Offer rejected successfully",
            ),
            400: OpenApiResponse(description="Application is not in OFFERED status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
    patch=extend_schema(
        summary="Reject job offer",
        description="Reject a job offer. The application must be in OFFERED status.",
        request=inline_serializer(
            "RejectOfferRequest",
            fields={
                "cover_letter": serializers.CharField(
                    required=False, default="",
                    help_text="Optional message to the recruiter",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=JobApplicationDetailSerializer,
                description="Offer rejected successfully",
            ),
            400: OpenApiResponse(description="Application is not in OFFERED status"),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Application not found"),
        },
    ),
)
class RejectOfferView(CandidateApplicationActionMixin, generics.UpdateAPIView):
    """
    Allows candidates to reject job offers.

    Sets the application status to the company's OFFER_REJECTED-category status
    (resolved from ApplicationStatusModel). Falls back to OFFER_REJECTED
    legacy enum if the flexible system is not available.
    """

    permission_classes = [IsAuthenticated, IsCandidatePermission]
    serializer_class = JobApplicationDetailSerializer

    def _get_company_offer_rejected_key(self, application):
        """Resolve the OFFER_REJECTED-category status key for this company."""
        rejected_status = ApplicationStatusModel.objects.filter(
            company=application.vacancy.company,
            category__key=StatusCategory.OFFER_REJECTED,
            is_active=True,
        ).first()
        if rejected_status:
            return rejected_status.key
        return ApplicationStatus.OFFER_REJECTED

    def _get_company_offered_key(self, application):
        """Resolve the OFFERED-category status key for this company."""
        offered_status = ApplicationStatusModel.objects.filter(
            company=application.vacancy.company,
            category__key=StatusCategory.OFFERED,
            is_active=True,
        ).first()
        if offered_status:
            return offered_status.key
        return ApplicationStatus.OFFERED

    def get_object(self):
        """
        Get the application with offer to reject.
        Optimized with select_related and prefetch_related to minimize database queries.
        """
        application = self._get_candidate_application()

        offered_key = self._get_company_offered_key(application)
        if application.status != offered_key:
            raise ValidationError(
                {"detail": _("Can only reject applications with OFFERED status")}
            )

        return application

    def update(self, request, *args, **kwargs):
        """
        Reject the offer by updating status to OFFER_REJECTED-category key.
        Optionally accepts a cover_letter field as a message to the recruiter.
        """
        application = self.get_object()
        candidate_message = request.data.get("cover_letter", "").strip()
        offer_rejected_key = self._get_company_offer_rejected_key(application)
        return self._apply_status_change(
            request,
            application=application,
            new_status=offer_rejected_key,
            success_message=_("Offer rejected successfully"),
            failure_message=_("Failed to reject offer"),
            notes="Offer rejected by candidate",
            candidate_message=candidate_message or None,
        )


apply_to_vacancy_view = ApplyToVacancyView.as_view()
candidate_application_list_view = CandidateApplicationsListView.as_view()
withdraw_application_view = WithdrawApplicationView.as_view()
reapply_to_vacancy_view = ReapplyToVacancyView.as_view()
accept_offer_view = AcceptOfferView.as_view()
reject_offer_view = RejectOfferView.as_view()
