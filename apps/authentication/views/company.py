from rest_framework import generics, filters
from rest_framework.generics import CreateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Prefetch
from django.db.models import Q

from django.db import transaction, IntegrityError
from django_filters.rest_framework import DjangoFilterBackend

import logging

from apps.authentication.models import Company, Recruiter
from apps.authentication.serializers import (
    CompanySerializer,
    CompanyRegistrationSerializer,
    CompanyProfileSerializer,
)
from apps.profiles.models import RecruiterProfile, CompanyProfile
from apps.authentication.services.consent_service import ConsentService
from apps.subscriptions.services import SubscriptionService
from core.responses import APIResponse
from utils import IsAdminRecruiter
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def _send_company_confirmation_email_task(company_id):
    logger.info("Sending confirm-company email for company %s", company_id)
    try:
        from apps.general.services.company_email_service import send_company_confirmation_emails
        result = send_company_confirmation_emails(
            company_ids=[str(company_id)],
            is_active=True,
        )
        sent = result.get("sent_emails", [])
        failed = result.get("failed_emails", [])
        logger.info(
            "Confirm-company emails for %s: %d sent, %d failed",
            company_id, len(sent), len(failed),
        )
    except Exception:
        logger.exception("Failed to send confirm-company email for company %s", company_id)


class RecruiterEmailConflictError(Exception):
    """Raised when recruiter email conflicts with an existing user email."""


class CompanyRegistrationView(CreateAPIView):
    serializer_class = CompanyRegistrationSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        company_free_plan = SubscriptionService.get_company_free_plan()
        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
                "company_free_plan": company_free_plan,
            },
        )
        serializer.is_valid(raise_exception=True)

        try:
            company = self.perform_create(serializer)
        except RecruiterEmailConflictError:
            return APIResponse.bad_request(
                message=_("A recruiter with this email already exists."),
                details=_("Please use a different email address for each recruiter."),
            )

        return APIResponse.created(
            data={"company_id": str(company.id)},
            message=_("Company registered successfully. Activation emails will be sent to all recruiters."),
        )

    @transaction.atomic
    def perform_create(self, serializer):
        validated_data = serializer.validated_data

        # Extract consent agreement flags
        company_agreed = validated_data.pop("company_agreed_to_all_consents", False)
        admin_agreed = validated_data.pop("admin_agreed_to_all_consents", False)

        # Create company
        company = Company.objects.create(
            name=validated_data["name"],
            domain=validated_data.get("domain_id"),
            tin=validated_data["inn"],
            file=self.request.FILES.get("file"),
        )

        # Create company profile with optional website and phone number
        website = validated_data.get("website") or ""
        phone_number = validated_data.get("phone_number") or ""
        CompanyProfile.objects.create(company=company, website=website, phone_number=phone_number)

        # Get IP and user agent for consent tracking
        ip_address = ConsentService.get_client_ip(self.request)
        user_agent = self.request.headers.get('User-Agent', '') if self.request else ''

        # Create company consent records if agreed
        if company_agreed:
            ConsentService.create_consents_for_entity(
                consenter=company,
                entity_type='company',
                ip_address=ip_address,
                user_agent=user_agent,
                request=self.request,
            )

        # Create admin recruiter with consents
        self._create_recruiter(
            email=validated_data["company_email"],
            company=company,
            level="Admin",
            agreed_to_all_consents=admin_agreed,
            ip_address=ip_address,
            user_agent=user_agent,
            request=self.request,
        )

        # Create additional recruiters (without consent - they will consent at set-password step)
        recruiter_emails = validated_data.get("recruiter_emails", [])
        for rec_data in recruiter_emails:
            email = rec_data.get("email")
            level = rec_data.get("level", "Recruiter")

            if email:
                self._create_recruiter(
                    email=email,
                    company=company,
                    level=level,
                    agreed_to_all_consents=False,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request=self.request,
                )

        # --- Auto-assign free subscription to the new company ---
        company_free_plan = serializer.context.get("company_free_plan")
        subscription = None
        if company_free_plan and company_free_plan.is_active:
            subscription = SubscriptionService.create_company_subscription(
                company,
                plan=company_free_plan,
                expire_existing=False,
            )
        if subscription is None:
            logger.warning(
                "Failed to create subscription for new company '%s' (ID: %s). "
                "Ensure the seed_subscriptions command has been run.",
                company.name,
                company.id,
            )

        # TEMPORARY: Send confirm-company email after registration.
        # The company remains is_active=False, but recruiters receive
        # set-password links so they can log in. The frontend restricts
        # access via the company_is_active flag returned at login.
        import django_rq
        django_rq.enqueue(_send_company_confirmation_email_task, str(company.id))

        # Notify Telegram partner topic about new company registration (async)
        from apps.authentication.tasks import send_partner_notification_task
        django_rq.enqueue(send_partner_notification_task, str(company.id))

        return company

    def _create_recruiter(
            self,
            email,
            company,
            level,
            agreed_to_all_consents=False,
            ip_address=None,
            user_agent='',
            request=None,
        ):
        """Helper method to create a recruiter with profile, unusable password, and consent records"""
        normalized_email = email.lower().strip()

        try:
            recruiter = Recruiter(
                email=normalized_email,
                company=company,
                is_active=True,
                is_recruiter=True,
            )
            recruiter.set_unusable_password()
            recruiter.save()
        except IntegrityError as exc:
            if self._is_recruiter_email_unique_violation(exc):
                raise RecruiterEmailConflictError() from exc
            raise

        RecruiterProfile.objects.create(recruiter=recruiter, level=level)

        # Create consent records for recruiter if they agreed
        if agreed_to_all_consents:
            ConsentService.create_consents_for_entity(
                consenter=recruiter,
                entity_type='recruiter',
                ip_address=ip_address or '0.0.0.0',
                user_agent=user_agent,
                request=request,
            )

        return recruiter

    @staticmethod
    def _is_recruiter_email_unique_violation(exc: IntegrityError) -> bool:
        """Return True only for unique violations on email during recruiter creation."""
        db_error = getattr(exc, "__cause__", None) or getattr(exc, "orig", None)
        diag = getattr(db_error, "diag", None)

        constraint_name = (getattr(diag, "constraint_name", "") or "").lower()
        table_name = (getattr(diag, "table_name", "") or "").lower()
        column_name = (getattr(diag, "column_name", "") or "").lower()

        if column_name == "email":
            return True

        if table_name in {"authentication_customuser", "customuser"} and "email" in constraint_name:
            return True

        # Fallback for DB drivers that don't expose diag details.
        message = str(exc).lower()
        return "email" in message and "unique" in message and "customuser" in message


# Keep existing views unchanged
class CompanyListView(generics.ListAPIView):
    queryset = Company.objects.filter(
        is_active=True
    ).select_related('domain').prefetch_related(
        Prefetch(
            'companyprofile',
            queryset=CompanyProfile.objects.all(),
            to_attr='company_profiles'
        ),
        Prefetch(
            'recruiters',
            queryset=Recruiter.objects.select_related('customuser_ptr').prefetch_related(
                Prefetch(
                    'recruiterprofile_set',
                    queryset=RecruiterProfile.objects.all()
                )
            ).order_by('date_joined'),
            to_attr='all_recruiters'
        )
    )
    serializer_class = CompanySerializer
    permission_classes = [AllowAny]

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]

    filterset_fields = ["id", "tin", "is_active"]
    ordering_fields = ["name"]
    ordering = ["name"]
    search_fields = ["name"]


class CompanyDetailView(generics.RetrieveAPIView):
    queryset = Company.objects.select_related('domain').prefetch_related(
        Prefetch(
            'companyprofile',
            queryset=CompanyProfile.objects.all(),
            to_attr='company_profiles'
        ),
    )
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated]


class CompanyProfileCreateView(CreateAPIView):
    serializer_class = CompanyProfileSerializer
    permission_classes = [IsAdminRecruiter]

    @staticmethod
    def _resolve_company_for_user(user):
        company_id = getattr(user, "company_id", None)
        if company_id:
            return Company.objects.filter(pk=company_id).first()

        user_id = getattr(user, "id", None)
        user_email = getattr(user, "email", None)
        if not user_id and not user_email:
            return None

        recruiter = Recruiter.objects.select_related("company").filter(
            Q(pk=user_id) | Q(email=user_email)
        ).first()
        if recruiter:
            return recruiter.company
        return None

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        company = self._resolve_company_for_user(request.user)

        if company is None:
            return APIResponse.bad_request(
                message=_("Authenticated user has no associated company."),
                details=_("Your account is not linked to any company."),
            )

        data = request.data.copy()
        data.pop("company", None)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # Use update_or_create to avoid duplicate profiles when a profile
        # was already created during company registration.
        existing_profile = CompanyProfile.objects.filter(company=company).first()
        if existing_profile:
            profile = serializer.update(existing_profile, serializer.validated_data)
        else:
            profile = serializer.save(company=company)

        return APIResponse.created(
            data={"profile_id": str(getattr(profile, "id", ""))},
            message=_("Company profile created successfully."),
        )


company_list_view = CompanyListView.as_view()
company_detail_view = CompanyDetailView.as_view()
company_create_view = CompanyRegistrationView.as_view()
company_profile_create_view = CompanyProfileCreateView.as_view()
