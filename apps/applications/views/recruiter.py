import logging
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q, Prefetch, Subquery, Count
from django.utils import timezone
from django.db import models, transaction
from django.utils.translation import gettext as _

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from utils import IsAdminRecruiter
from utils.recruiter_permission import IsRecruiterPermission
from utils.company_permission import IsCompanyApproved
from utils.view_mixins import RecruiterMixin
from utils.language import get_request_language
from apps.hr_templates.constants import render_template_variables

from apps.profiles.models import RecruiterProfile

from apps.applications.serializers import (
    CompanyCandidatesApplicationSerializer,
    JobApplicationUpdateSerializer,
    HiredCandidateSerializer,
)
from apps.applications.serializers.candidate_company import (
    CandidateCompanyApplicationsResponseSerializer,
)
from apps.applications.services.candidate_company_applications import (
    CandidateCompanyApplicationsService,
)
from apps.applications.models import JobApplication, ApplicationDocument
from apps.applications.models.choices import ApplicationStatus
from apps.applications.models import ApplicationStatusModel, StatusCategory
from apps.conversations.services import create_status_change_message
from apps.notifications.services import ApplicationNotificationService
from apps.resumes.models import Resume, ResumeSkill
from apps.vacancies.models import VacancySkill

from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound, ValidationError

logger = logging.getLogger(__name__)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="vacancy_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="Filter candidates by specific vacancy. If not provided, returns candidates for all company vacancies.",
            required=False,
        ),
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by application status (e.g., pending, accepted, rejected)",
            required=False,
        ),
        OpenApiParameter(
            name="salary_min",
            type=OpenApiTypes.DECIMAL,
            location=OpenApiParameter.QUERY,
            description="Minimum salary filter (uses candidate resume salary with currency conversion)",
            required=False,
        ),
        OpenApiParameter(
            name="salary_max",
            type=OpenApiTypes.DECIMAL,
            location=OpenApiParameter.QUERY,
            description="Maximum salary filter (uses candidate resume salary with currency conversion)",
            required=False,
        ),
        OpenApiParameter(
            name="currency",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Currency for salary filter (USD, UZS, EUR, RUB). Defaults to UZS.",
            required=False,
        ),
        OpenApiParameter(
            name="recruiter_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="Filter by vacancy creator (recruiter)",
            required=False,
        ),
        OpenApiParameter(
            name="applied_from",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filter applications from a specific date (YYYY-MM-DD format)",
            required=False,
        ),
        OpenApiParameter(
            name="applied_to",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filter applications until a specific date (YYYY-MM-DD format)",
            required=False,
        ),
        OpenApiParameter(
            name="skills",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter candidates by skills (comma-separated skill names)",
            required=False,
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search by candidate name or specialty",
            required=False,
        ),
        OpenApiParameter(
            name="ai_fail",
            type=OpenApiTypes.BOOL,
            location=OpenApiParameter.QUERY,
            description="If true, only show candidates auto-rejected by AI evaluation (AI_FAILED status)",
            required=False,
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=CompanyCandidatesApplicationSerializer(many=True),
            description="Company candidates list retrieved successfully",
        ),
        400: OpenApiResponse(description="Validation error"),
        401: OpenApiResponse(description="Unauthorized"),
        404: OpenApiResponse(description="Recruiter profile not found"),
    },
    description="Shows all applications from candidates who have applied to vacancies in the recruiter's company. "
                "If vacancy_id is provided, shows applications for that specific vacancy. "
                "Otherwise, shows all candidates across all company vacancies."
)
class CompanyCandidatesListView(RecruiterMixin, generics.ListAPIView):
    """
    Shows all applications from candidates who have applied to vacancies in the recruiter's company.

    If vacancy_id is provided as a query parameter, shows applications for that specific vacancy.
    Otherwise, shows the latest application for each unique candidate across all company vacancies,
    giving recruiters a comprehensive view of their candidate pool.

    Supports filtering by:
    - vacancy_id: Filter by specific vacancy (optional)
    - status: Filter by application status
    - salary_min: Minimum candidate salary expectation (UZS)
    - salary_max: Maximum candidate salary expectation (UZS)
    - recruiter_id: Filter by vacancy creator (filters by vacancy__created_by)
    - applied_from: Filter applications from a specific date (YYYY-MM-DD format)
    - applied_to: Filter applications until a specific date (YYYY-MM-DD format)
    - skills: Filter candidates by skills (comma-separated skill names)
    - search: Search by candidate name or specialty
    """

    serializer_class = CompanyCandidatesApplicationSerializer
    permission_classes = [IsAuthenticated]
    _serializer_context_cache = None
    _ai_failed_status_cache = False

    def _get_ai_failed_status(self):
        """The company's AI-rejected status (None when it has none), cached."""
        if self._ai_failed_status_cache is False:
            recruiter = self.get_recruiter()
            self._ai_failed_status_cache = (
                ApplicationStatusModel.objects.filter(
                    company=recruiter.company,
                    category__key=StatusCategory.AI_FAILED,
                    is_active=True,
                ).first()
                if recruiter.company
                else None
            )
        return self._ai_failed_status_cache

    def _wants_ai_failed(self):
        """True when the request asks for the AI-rejected tab."""
        ai_fail = self.request.query_params.get("ai_fail")
        application_status = self.request.query_params.get("status")
        ai_failed_status = self._get_ai_failed_status()
        return bool(
            (ai_fail and ai_fail.lower() in ('true', '1'))
            or (ai_failed_status and application_status == ai_failed_status.key)
        )

    @staticmethod
    def _get_resume_skill_queryset():
        return ResumeSkill.objects.select_related("skill")

    @staticmethod
    def _get_vacancy_skill_queryset():
        return VacancySkill.objects.select_related("skill")

    @staticmethod
    def _get_document_prefetch():
        return Prefetch(
            "documents",
            queryset=ApplicationDocument.objects.only(
                "id",
                "application_id",
                "document_type",
                "title",
                "file",
                "file_size",
                "created_at",
            ).order_by("-created_at"),
        )

    def get_queryset(self):
        """
        Return applications from candidates who have applied to vacancies in the company.
        
        If vacancy_id is provided, returns all applications for that vacancy.
        Otherwise, returns the latest application for each unique candidate to avoid duplicates.
        """
        vacancy_id = self.request.query_params.get("vacancy_id")
        application_status = self.request.query_params.get("status")
        salary_min = self.request.query_params.get("salary_min")
        salary_max = self.request.query_params.get("salary_max")
        currency = self.request.query_params.get("currency")
        recruiter_id = self.request.query_params.get("recruiter_id")
        applied_from = self.request.query_params.get("applied_from")
        applied_to = self.request.query_params.get("applied_to")
        skills = self.request.query_params.get("skills")
        search = self.request.query_params.get("search")
        ai_fail = self.request.query_params.get("ai_fail")

        # Validate currency against allowed values to prevent path traversal
        ALLOWED_CURRENCIES = {"UZS", "USD", "EUR", "RUB"}
        if currency:
            currency = currency.upper().strip()
            if currency not in ALLOWED_CURRENCIES:
                raise ValidationError(
                    f"Invalid currency. Allowed values: {', '.join(sorted(ALLOWED_CURRENCIES))}"
                )

        # Validate salary values format early to return clear 400 responses
        if salary_min is not None:
            try:
                Decimal(str(salary_min))
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError(_("Invalid salary_min format. Expected a numeric value."))

        if salary_max is not None:
            try:
                Decimal(str(salary_max))
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError(_("Invalid salary_max format. Expected a numeric value."))

        # Get recruiter (cached by RecruiterMixin)
        recruiter = self.get_recruiter()

        # Unapproved companies see hardcoded demo applications — no DB queries
        if not recruiter.company or not recruiter.company.is_active:
            return JobApplication.objects.none()

        base_queryset = JobApplication.objects.filter(
            vacancy__company=recruiter.company,
            is_demo=False,
        ).exclude(
            status=ApplicationStatus.WITHDRAWN
        )

        # Apply vacancy filter if provided
        if vacancy_id:
            try:
                uuid.UUID(str(vacancy_id))
                queryset = base_queryset.filter(vacancy__id=vacancy_id)
            except (ValueError, TypeError):
                raise ValidationError(_("Invalid vacancy_id format. Expected a valid UUID."))
            # For specific vacancy, order by application date
            queryset = queryset.order_by("-applied_at")
        else:
            # For all vacancies, keep only the latest application per candidate.
            latest_application_ids = base_queryset.order_by(
                "candidate_id",
                "-applied_at",
                "-id",
            ).distinct("candidate_id").values("id")
            queryset = JobApplication.objects.filter(
                id__in=Subquery(latest_application_ids)
            ).order_by("candidate_id", "-applied_at", "-id")

        # Apply status filter if provided
        if application_status:
            if application_status not in [status.value for status in ApplicationStatus]:
                raise ValidationError(f"Invalid status: {application_status}")
            queryset = queryset.filter(status=application_status)

        # AI-rejected candidates have their own dedicated view (ai_fail=true),
        # so exclude them from the general listing unless explicitly requested.
        ai_failed_status = self._get_ai_failed_status()
        wants_ai_failed = self._wants_ai_failed()
        if ai_failed_status and not wants_ai_failed:
            queryset = queryset.exclude(status=ai_failed_status.key)

        # Apply salary range filter using resume salary with currency conversion
        if salary_min or salary_max:
            from utils.currency_converter import filter_applications_by_resume_salary
            queryset = filter_applications_by_resume_salary(
                queryset, salary_min, salary_max, currency
            )

        # Apply recruiter filter (filter by vacancy creator)
        if recruiter_id:
            try:
                # Validate that recruiter_id is a valid UUID
                uuid.UUID(str(recruiter_id))
                queryset = queryset.filter(vacancy__created_by__id=recruiter_id)
            except (ValueError, TypeError):
                raise ValidationError(_("Invalid recruiter_id format. Expected a valid UUID."))

        # Apply application date range filters
        if applied_from:
            try:
                from_date = datetime.strptime(applied_from, "%Y-%m-%d").date()
                queryset = queryset.filter(applied_at__date__gte=from_date)
            except ValueError:
                raise ValidationError(_("Invalid applied_from format. Use YYYY-MM-DD."))

        if applied_to:
            try:
                to_date = datetime.strptime(applied_to, "%Y-%m-%d").date()
                queryset = queryset.filter(applied_at__date__lte=to_date)
            except ValueError:
                raise ValidationError(_("Invalid applied_to format. Use YYYY-MM-DD."))

        # Apply skills filter
        if skills:
            skills_list = [skill.strip() for skill in skills.split(",") if skill.strip()]
            if skills_list:
                skill_q = Q()
                for skill_name in skills_list:
                    skill_q |= Q(skills__name__icontains=skill_name)

                candidate_ids_with_skills = Resume.objects.filter(
                    candidate__applications__vacancy__company=recruiter.company
                ).filter(
                    skill_q
                ).order_by("candidate_id").values("candidate_id").distinct()
                queryset = queryset.filter(candidate_id__in=models.Subquery(candidate_ids_with_skills))

        # Apply search filter
        if search:
            search_terms = search.strip().split()
            search_q = Q()
            for term in search_terms:
                term_q = Q(
                    Q(candidate__candidateprofile__full_name__icontains=term) |
                    Q(resume_used__title__icontains=term)
                )
                search_q &= term_q
            queryset = queryset.filter(search_q)

        # Apply AI_FAILED filter
        if ai_fail and ai_fail.lower() in ('true', '1'):
            if ai_failed_status:
                queryset = queryset.filter(status=ai_failed_status.key)
            else:
                queryset = queryset.none()

        resume_skill_queryset = self._get_resume_skill_queryset()
        vacancy_skill_queryset = self._get_vacancy_skill_queryset()

        return queryset.select_related(
            "candidate",
            "candidate__candidateprofile",
            "resume_used",
            "vacancy",
            "vacancy__company",
            "ai_evaluation",
            "vacancy__created_by",
            "vacancy_skill_roadmap",
        ).prefetch_related(
            self._get_document_prefetch(),
            Prefetch("vacancy__vacancyskill_set", queryset=vacancy_skill_queryset),
            Prefetch("resume_used__resume_skills", queryset=resume_skill_queryset),
            Prefetch(
                "candidate__resumes",
                queryset=Resume.objects.filter(is_main=True).only(
                    "id",
                    "candidate_id",
                    "title",
                    "current_salary",
                    "salary_currency",
                    "salary_hide",
                    "is_main",
                ).prefetch_related(
                    Prefetch("resume_skills", queryset=self._get_resume_skill_queryset())
                ),
                to_attr="prefetched_main_resumes",
            ),
        ).defer(
            "candidate__password",
            "candidate__last_login",
            "candidate__is_superuser",
            "candidate__is_staff",
            "candidate__is_candidate",
            "candidate__is_recruiter",
            "candidate__date_joined",
            "candidate__timezone",
            "candidate__preferred_language",
            "candidate__faculty_id",
            "candidate__date_of_birth",
            "candidate__is_vault_verified",
            "candidate__onboarding_progress",
            "resume_used__created_at",
            "resume_used__updated_at",
            "resume_used__description",
            "resume_used__position",
            "resume_used__domain_id",
            "resume_used__work_status",
            "resume_used__current_company_name",
            "resume_used__current_company_id",
            "resume_used__current_position",
            "resume_used__employment_start_date",
            "resume_used__is_active",
            "resume_used__is_main",
            "resume_used__combined_text_en",
            "resume_used__embedding",
            "resume_used__is_embedded",
            "vacancy__created_at",
            "vacancy__updated_at",
            "vacancy__domain_id",
            "vacancy__experience",
            "vacancy__contact_email",
            "vacancy__contact_phone",
            "vacancy__salary_min",
            "vacancy__salary_max",
            "vacancy__salary_currency",
            "vacancy__employment_format",
            "vacancy__about_us",
            "vacancy__requirements",
            "vacancy__responsibilities",
            "vacancy__additional_info",
            "vacancy__is_active",
            "vacancy__number_of_positions",
            "vacancy__combined_text_en",
            "vacancy__embedding",
            "vacancy__is_embedded",
            "vacancy__expire",
            "vacancy__location",
            "vacancy__longitude",
            "vacancy__latitude",
            "vacancy__company__created_at",
            "vacancy__company__updated_at",
            "vacancy__company__domain_id",
            "vacancy__company__tin",
            "vacancy__company__file",
            "vacancy__company__is_active",
        ).annotate(
            discussion_count=Count("internal_discussions"),
        )

    def get_serializer_context(self):
        """
        Extend context with pre-fetched status metadata for the company.

        Passes compact lookup maps so the serializer can resolve custom status
        labels and terminal-state checks in a single batch query instead of
        one query per application.

        Memoized on the view instance (fresh per-request in DRF) because DRF's
        own ``GenericAPIView.get_serializer()`` calls this method again via
        ``kwargs.setdefault('context', self.get_serializer_context())`` —
        Python evaluates that default argument eagerly even when 'context' is
        already in kwargs, so without caching the two status/recruiter queries
        below would run twice per request for no benefit.
        """
        if self._serializer_context_cache is not None:
            return self._serializer_context_cache

        context = super().get_serializer_context()
        recruiter = self.get_recruiter()
        language = get_request_language()
        statuses = list(ApplicationStatusModel.objects.filter(
            company=recruiter.company,
            is_active=True,
        ).select_related("category").only(
            "id",
            "key",
            "label",
            "color",
            "translations",
            "company_id",
            "category_id",
            "category__is_terminal",
            "category__key",
        ))
        recruiter_name_map = {}
        recruiter_profiles = RecruiterProfile.objects.filter(
            recruiter__company=recruiter.company,
        ).only(
            "recruiter_id",
            "full_name",
        ).order_by("recruiter_id", "id")
        for profile in recruiter_profiles:
            recruiter_name_map.setdefault(profile.recruiter_id, profile.full_name)

        context["status_labels"] = {
            s.key: s.get_localized_label(language) for s in statuses
        }
        context["status_terminal_map"] = {
            s.key: s.category.is_terminal for s in statuses
        }
        context["status_category_map"] = {
            s.key: s.category.key for s in statuses
        }
        context["status_color_map"] = {
            s.key: s.color for s in statuses
        }
        context["recruiter_name_map"] = recruiter_name_map
        # Kept around (not part of the serialized context payload) so
        # get_serializer() can hand the same pre-fetched data to the
        # summary-map service instead of it re-querying the same tables.
        context["_status_lookup"] = statuses
        self._serializer_context_cache = context
        return context

    def get_serializer(self, *args, **kwargs):
        """
        Inject the per-candidate company-applications summary map for the
        current page so every row can show the total application count and
        the best-match AI score/status without extra queries per row.
        """
        if args and kwargs.get("many") and args[0]:
            candidate_ids = {
                app.candidate_id
                for app in args[0]
                if isinstance(app, JobApplication)
            }
            if candidate_ids:
                # Copy instead of mutating the memoized context dict from
                # get_serializer_context() (self._serializer_context_cache) —
                # otherwise company_applications_map would leak into any
                # later read of that cache within the same request.
                context = dict(kwargs.get("context") or self.get_serializer_context())
                recruiter = self.get_recruiter()
                # The dropdown must mirror the tab it is opened from: the
                # general listing hides AI-rejected applications (they live on
                # the AI-rejected tab) and that tab shows only those.
                ai_failed_status = self._get_ai_failed_status()
                ai_failed_keys = [ai_failed_status.key] if ai_failed_status else None
                wants_ai_failed = self._wants_ai_failed()
                context["company_applications_map"] = (
                    CandidateCompanyApplicationsService.get_summary_map(
                        recruiter.company,
                        candidate_ids,
                        language=get_request_language(),
                        status_lookup=context.get("_status_lookup"),
                        recruiter_name_map=context.get("recruiter_name_map"),
                        exclude_status_keys=(
                            None if wants_ai_failed else ai_failed_keys
                        ),
                        only_status_keys=(
                            ai_failed_keys if wants_ai_failed else None
                        ),
                    )
                )
                kwargs["context"] = context
        return super().get_serializer(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        recruiter = self.get_recruiter()
        if not recruiter.company or not recruiter.company.is_active:
            from apps.vacancies.services.demo_data import get_demo_applications
            from apps.skills.localization import user_preferred_language
            from rest_framework.response import Response
            language = user_preferred_language(request.user)
            applications = get_demo_applications(language)
            return Response({
                "count": len(applications),
                "next": None,
                "previous": None,
                "limit": 20,
                "offset": 0,
                "results": applications,
            })
        return super().list(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        """
        Handle GET request to list applications from candidates who have applied to company vacancies.
        """
        return super().get(request, *args, **kwargs)


class UpdateApplicationStatusView(RecruiterMixin, generics.UpdateAPIView):
    """
    Allows recruiters to update the status of job applications for their own vacancies.

    This is like the "case management" system that HR departments use
    to track candidates through their hiring pipeline. Recruiters can only
    change application statuses for vacancies they own, and we maintain an audit trail.

    Also handles Kanban board operations:
    - Moving applications between columns (status change)
    - Reordering within a column (position change)
    - Combined status and position updates for drag-and-drop

    Access Control:
    - Recruiters: Can update applications only for vacancies they created
    - Returns 400 BadRequest if trying to update application for vacancy they don't own
    """

    serializer_class = JobApplicationUpdateSerializer
    permission_classes = [IsRecruiterPermission, IsCompanyApproved]

    def get_object(self):
        """
        Get the application to update with permission checking.
        Optimized to reduce redundant queries.
        Uses select_for_update() to prevent race conditions during concurrent Kanban operations.
        
        Ensures the recruiter owns the vacancy (created_by = recruiter).
        
        Note: We only select_related on non-nullable foreign keys with select_for_update()
        because FOR UPDATE cannot be applied to nullable outer joins.
        """
        application_id = self.kwargs.get("application_id")
        recruiter = self.get_recruiter()

        try:
            # Only select_related on non-nullable FKs (vacancy, candidate) with select_for_update
            # We need to select_related vacancy to check ownership
            # Nullable FKs (resume_used, last_updated_by) will be loaded separately if needed
            application = JobApplication.objects.select_related(
                "vacancy__company", "candidate"
            ).select_for_update().get(
                id=application_id
            )
        except JobApplication.DoesNotExist:
            raise NotFound("Application not found")

        if application.vacancy.company_id != recruiter.company_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "You can only update applications for your own company vacancies."
            )

        # Check if the recruiter owns the vacancy
        if application.vacancy.created_by_id != recruiter.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "You can only update applications for vacancies you created."
            )

        return application

    @staticmethod
    def _is_new_status_hired(application, new_status):
        """Check if new_status maps to HIRED category in the flexible system."""
        try:
            status_model = ApplicationStatusModel.objects.filter(
                company=application.vacancy.company,
                key=new_status,
                is_active=True,
            ).select_related('category').first()
            if status_model:
                from apps.applications.models.status import StatusCategory
                return status_model.category.key == StatusCategory.HIRED
        except Exception:
            logger.exception(
                "Failed to resolve whether status '%s' is HIRED for application '%s'",
                new_status,
                getattr(application, "id", None),
            )
        return False

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Wrap the entire update operation in a single transaction so that
        `get_object()` (with select_for_update) and `perform_update()` run
        within the same transactional scope.
        """
        return super().update(request, *args, **kwargs)

    @staticmethod
    def _ensure_sequential_positions(company, status_key, application_id=None):
        """
        Ensure all applications in a kanban column have sequential, unique
        positions (0, 1, 2, …).

        New applications default to ``kanban_position=0``, which means several
        cards can share the same position value.  Before running the
        position-shift logic (which assumes sequential positions), we must
        normalise the column.  The method is a no-op when positions are
        already sequential.

        Args:
            company: The company the column belongs to.
            status_key: The status key identifying the column.
            application_id: If provided, return the normalised position of this
                application within the freshly ordered list.

        Returns:
            The normalised position (int) of ``application_id`` after ordering,
            or ``None`` when ``application_id`` is not supplied / not found.
        """
        from django.db.models import Case, When
        from django.db.models import IntegerField as _IntField

        apps = list(
            JobApplication.objects.filter(
                vacancy__company=company,
                status=status_key,
            )
            .order_by("kanban_position", "applied_at", "id")
            .values_list("id", "kanban_position")
        )

        if not apps:
            return None

        actual_positions = [position for _, position in apps]
        expected_positions = list(range(len(apps)))

        # Find the index of the target application in the ordered list
        target_index = None
        for idx, (app_id, position) in enumerate(apps):
            if app_id == application_id:
                target_index = idx
                break

        if actual_positions == expected_positions:
            # Already sequential — nothing to do
            return target_index

        # Positions are not sequential (e.g., multiple apps share position 0).
        # Rebuild them with a single bulk-UPDATE using CASE/WHEN.
        cases = [When(id=app_id, then=idx) for idx, (app_id, _) in enumerate(apps)]
        JobApplication.objects.filter(
            id__in=[app_id for app_id, _ in apps]
        ).update(
            kanban_position=Case(*cases, output_field=_IntField())
        )

        return target_index

    def perform_update(self, serializer):
        """
        Update the application with proper audit trail, validation, and Kanban reordering.

        Handles both simple status updates and Kanban drag-and-drop operations.

        Position logic
        --------------
        Normalization (``_ensure_sequential_positions``) is run whenever a
        ``kanban_position`` is explicitly provided, *even when the submitted
        position equals the application's current stored value*.  This is
        required because new applications all default to position 0, so
        multiple cards can legitimately share that value.  Without
        normalization the shift queries would produce incorrect results.
        """
        recruiter = self.get_recruiter()
        application = serializer.instance

        # Get the update information
        new_status = serializer.validated_data.get("status")
        new_position = serializer.validated_data.get("kanban_position")
        notes = serializer.validated_data.get("recruiter_notes", "")
        title = serializer.validated_data.get("title", "")

        vacancy = application.vacancy
        company = vacancy.company

        # Render template variables in recruiter_notes before saving
        if notes:
            candidate = application.candidate
            notes = render_template_variables(notes, candidate, vacancy, company)

        old_status = application.status
        old_position = application.kanban_position
        status_changed = bool(new_status) and old_status != new_status

        # ------------------------------------------------------------------ #
        # Kanban position / status reordering                                  #
        # ------------------------------------------------------------------ #
        # Always enter this block when a position is explicitly provided,
        # regardless of whether it equals the current stored value.  Duplicate
        # default positions (all 0) would otherwise prevent normalization from
        # running, leaving the column in an inconsistent state.
        if new_position is not None or status_changed:
            # Normalise the current (old) column so positions are sequential
            # (0, 1, 2, …).  This is a no-op when they already are.
            normalised_old = self._ensure_sequential_positions(
                company, old_status, application_id=application.id
            )
            if normalised_old is not None:
                old_position = normalised_old

            # Re-evaluate position_changed against the *normalised* position.
            position_changed = new_position is not None and old_position != new_position

            if status_changed and new_position is not None:
                # Moving to a different column at an explicit position.
                # Normalise the target column first so the shift is correct.
                self._ensure_sequential_positions(company, new_status)

                # 1. Close the gap in the old column.
                JobApplication.objects.filter(
                    vacancy__company=company,
                    status=old_status,
                    kanban_position__gt=old_position,
                ).exclude(id=application.id).update(
                    kanban_position=models.F("kanban_position") - 1
                )

                # 2. Make room at new_position in the target column.
                JobApplication.objects.filter(
                    vacancy__company=company,
                    status=new_status,
                    kanban_position__gte=new_position,
                ).exclude(id=application.id).update(
                    kanban_position=models.F("kanban_position") + 1
                )

            elif position_changed and not status_changed:
                # Reordering within the same column.
                current_status = old_status

                if old_position < new_position:
                    # Moving down: pull up items between old and new positions.
                    JobApplication.objects.filter(
                        vacancy__company=company,
                        status=current_status,
                        kanban_position__gt=old_position,
                        kanban_position__lte=new_position,
                    ).exclude(id=application.id).update(
                        kanban_position=models.F("kanban_position") - 1
                    )
                else:
                    # Moving up: push down items between new and old positions.
                    JobApplication.objects.filter(
                        vacancy__company=company,
                        status=current_status,
                        kanban_position__gte=new_position,
                        kanban_position__lt=old_position,
                    ).exclude(id=application.id).update(
                        kanban_position=models.F("kanban_position") + 1
                    )

            elif status_changed and new_position is None:
                # Status change without an explicit position: append to the
                # end of the target column.  Normalise first so max() reflects
                # the true last sequential slot.
                self._ensure_sequential_positions(company, new_status)

                max_position_result = JobApplication.objects.filter(
                    vacancy__company=company,
                    status=new_status,
                ).exclude(id=application.id).aggregate(max_pos=models.Max('kanban_position'))

                max_position = max_position_result['max_pos']
                serializer.validated_data["kanban_position"] = (
                    0 if max_position is None else max_position + 1
                )

                # Close the gap in the old column.
                JobApplication.objects.filter(
                    vacancy__company=company,
                    status=old_status,
                    kanban_position__gt=old_position,
                ).exclude(id=application.id).update(
                    kanban_position=models.F("kanban_position") - 1
                )

        # ------------------------------------------------------------------ #
        # Persist the change                                                   #
        # ------------------------------------------------------------------ #
        if status_changed:
            try:
                # Validate the transition before committing anything.
                application.validate_status_transition(new_status, user_type="recruiter")

                # Append timestamped recruiter notes for the audit trail.
                if notes:
                    timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                    status_change_note = (
                        f"[{timestamp}] Status changed from {old_status} to {new_status} "
                        f"by recruiter: {notes}"
                    )
                    if application.recruiter_notes:
                        application.recruiter_notes += f"\n\n{status_change_note}"
                    else:
                        application.recruiter_notes = status_change_note

                # Update the in-memory instance fields before saving.
                application.status = new_status
                if new_position is not None:
                    application.kanban_position = new_position
                elif "kanban_position" in serializer.validated_data:
                    application.kanban_position = serializer.validated_data["kanban_position"]
                application.last_updated_by = recruiter

                # Cache the information that save() needs to set timestamps
                # (in_review_at / hired_at) so it can skip two extra DB queries.
                application._cached_old_status = old_status
                application._cached_is_hired = (
                    new_status == ApplicationStatus.OFFER_ACCEPTED
                    or self._is_new_status_hired(application, new_status)
                )

                application.save()

                # Mirror the status change as a conversation message.
                create_status_change_message(
                    application=application,
                    old_status=old_status,
                    new_status=new_status,
                    recruiter_note=notes if notes else None,
                    changed_by="RECRUITER",
                    title=title if title else None,
                )

                try:
                    ApplicationNotificationService.notify_candidate_status_updated(
                        application,
                        old_status=old_status,
                        new_status=new_status,
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify candidate about status change for application %s",
                        application.id,
                    )

            except ValidationError:
                raise

        else:
            # No status change — build the update dict and apply it directly to
            # the DB row.  Using filter().update() avoids calling model.save()
            # which would trigger two extra SELECT queries
            # (old_instance lookup + _is_hired_status check) for no benefit
            # when only position / notes / dates are changing.
            update_fields = {}
            if new_position is not None:
                update_fields["kanban_position"] = new_position
            if notes:
                timestamp = timezone.now().strftime("%Y-%m-%d %H:%M")
                timestamped_note = f"[{timestamp}] {notes}"
                update_fields["recruiter_notes"] = (
                    application.recruiter_notes + f"\n\n{timestamped_note}"
                    if application.recruiter_notes
                    else timestamped_note
                )
            for field in ["earliest_start_date"]:
                if field in serializer.validated_data:
                    update_fields[field] = serializer.validated_data[field]
            update_fields["last_updated_by"] = recruiter

            JobApplication.objects.filter(pk=application.pk).update(**update_fields)

            # Keep the in-memory instance consistent so the response reflects
            # the new values (DRF returns serializer.data after perform_update).
            for key, value in update_fields.items():
                setattr(application, key, value)


class ApplicationStatusListView(generics.ListAPIView):
    """
    Lists all possible application statuses.

    This is useful for populating dropdowns or status selection UIs
    when recruiters are updating application statuses.
    
    Supports localization via Accept-Language header:
    - en: English (default)
    - ru: Russian
    - uz: Uzbek
    """

    permission_classes = [IsAuthenticated]
    serializer_class = None  # No serializer needed for simple list

    def get(self, request, *args, **kwargs):
        """
        Return the list of application statuses in the requested language.
        """
        language = get_request_language()
        statuses = ApplicationStatus.get_localized_statuses(language)
        return Response({"statuses": statuses})


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search by candidate's full name or vacancy title (case-insensitive partial match)",
            required=False,
        ),
    ],
    description="Returns the list of candidates hired by the company. "
                "Includes both legacy OFFER_ACCEPTED and HIRED-category statuses. "
                "Only accessible by admin recruiters. Supports filtering by candidate name and vacancy title "
                "using the 'search' parameter. Results are paginated."
)
class HiredCandidatesListView(RecruiterMixin, generics.ListAPIView):
    """
    API endpoint that returns the list of candidates hired by the company.
    
    This endpoint is only accessible by admin recruiters and returns:
    - Candidate full_name (from CandidateProfile)
    - Vacancy title (the position they were hired for)
    - hired_at (date/time when the candidate was hired)
    - Candidate phone_number
    - Candidate photo
    - Vacancy ID
    - Resume ID (resume_used or main/first resume)
    
    Supports filtering by:
    - search: Search by candidate's full name or vacancy title
    
    Results are paginated using the default pagination configuration.
    """

    serializer_class = HiredCandidateSerializer
    permission_classes = [IsAuthenticated, IsAdminRecruiter]

    def get_queryset(self):
        """
        Return hired applications for the recruiter's company.
        Includes both legacy OFFER_ACCEPTED statuses and statuses that map
        to the HIRED analytics category.
        Optimized with prefetch_related to avoid N+1 queries for resumes.
        """
        from django.db.models import Prefetch
        from apps.resumes.models import Resume
        from apps.applications.services.hiring_analytics_service import HiringAnalyticsService

        recruiter = self.get_recruiter()
        hired_keys = HiringAnalyticsService.get_hired_status_keys(recruiter.company_id)

        # Get applications with hired status for company's vacancies
        # Using select_related for one-to-one relationship (candidateprofile) for efficient JOIN
        # Using prefetch_related for resumes to avoid N+1 queries
        queryset = JobApplication.objects.select_related(
            'candidate',
            'candidate__candidateprofile',
            'vacancy',
            'resume_used',
        ).prefetch_related(
            Prefetch(
                'candidate__resumes',
                queryset=Resume.objects.filter(is_active=True).order_by('-is_main', '-created_at'),
                to_attr='prefetched_resumes',
            )
        ).filter(
            vacancy__company=recruiter.company,
            status__in=hired_keys,
        ).order_by('-hired_at')

        # Apply unified search filter
        search = self.request.query_params.get('search')

        if search:
            # Search in both candidate full name and vacancy title
            queryset = queryset.filter(
                Q(candidate__candidateprofile__full_name__icontains=search) |
                Q(vacancy__title__icontains=search)
            )

        return queryset


class CandidateCompanyApplicationsBaseView(RecruiterMixin, APIView):
    """
    Shared implementation for the candidate-applications detail endpoints.

    Returns every application the candidate submitted to the requesting
    recruiter's company, ordered by AI evaluation score (best match first).
    Concrete subclasses exist so the candidates list and the kanban board
    each get their own URL, while the logic lives in one service.

    AI-rejected applications are left out unless ``?ai_fail=true`` is passed,
    mirroring the lists these dropdowns are opened from: those applications
    belong to the AI-rejected tab.

    Access control:
    - Only recruiters (including admin recruiters) can call this endpoint.
    - Data is always scoped to the recruiter's own company; candidates of
      other companies resolve to 404.
    """

    permission_classes = [IsRecruiterPermission]

    def get(self, request, candidate_id, *args, **kwargs):
        recruiter = self.get_recruiter()
        company = recruiter.company

        if not company or not company.is_active:
            raise NotFound(_("Candidate applications are not available."))

        ai_fail = request.query_params.get("ai_fail")
        wants_ai_failed = bool(ai_fail and ai_fail.lower() in ('true', '1'))
        ai_failed_keys = (
            CandidateCompanyApplicationsService.get_ai_failed_status_keys(company)
            or None
        )

        data = CandidateCompanyApplicationsService.get_candidate_applications(
            company,
            candidate_id,
            language=get_request_language(),
            exclude_status_keys=None if wants_ai_failed else ai_failed_keys,
            only_status_keys=ai_failed_keys if wants_ai_failed else None,
        )
        if data is None:
            raise NotFound(_("Candidate has no applications in your company."))

        return Response(data)


@extend_schema(
    responses={
        200: OpenApiResponse(
            response=CandidateCompanyApplicationsResponseSerializer,
            description="All applications of the candidate to the company's vacancies, best AI match first",
        ),
        403: OpenApiResponse(description="Only recruiters can access this endpoint"),
        404: OpenApiResponse(description="Candidate has no applications in this company"),
    },
    description="Candidates list detail: returns every application the candidate submitted to the "
                "recruiter's company, ordered by AI evaluation score (highest first, unscored last). "
                "Each entry contains the vacancy title, applied date (dd.mm.yyyy), AI score, "
                "localized status and the recruiter assigned to the vacancy (Vacancy.created_by). "
                "Visible only to recruiters/admins of the same company.",
)
class CompanyCandidateApplicationsView(CandidateCompanyApplicationsBaseView):
    """Candidates-list flavour of the candidate applications detail endpoint."""


company_candidates_list_view = CompanyCandidatesListView.as_view()
company_candidate_applications_view = CompanyCandidateApplicationsView.as_view()
update_application_status_view = UpdateApplicationStatusView.as_view()
application_status_list_view = ApplicationStatusListView.as_view()
hired_candidates_list_view = HiredCandidatesListView.as_view()
