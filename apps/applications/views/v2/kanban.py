"""
v2 kanban views.

Kanban board view for job applications — v2 only.
Returns applications grouped by status with pagination per column.
"""

import uuid

from collections import defaultdict

from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db.models import Q

from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from utils.view_mixins import RecruiterMixin

from apps.applications.models import JobApplication, ApplicationStatus
from apps.applications.serializers import (
    KanbanApplicationSerializer,
    KanbanResponseSerializer,
)
from utils import get_candidate_ids_by_skills


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="vacancy_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description="Filter applications by specific vacancy. If not provided, returns applications for all company vacancies.",
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Number of applications per column. Defaults to 20 for initial load.",
            required=False,
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Page number for pagination. Defaults to 1.",
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
    ],
    responses={
        200: OpenApiResponse(
            response=KanbanResponseSerializer,
            description="Kanban board data with applications grouped by status"
        ),
        400: OpenApiResponse(description="Validation error"),
        401: OpenApiResponse(description="Unauthorized"),
        404: OpenApiResponse(description="Recruiter profile not found"),
    },
    description="Returns applications grouped by status for Kanban board display. "
                "Each status column contains paginated applications ordered by their kanban_position. "
                "Uses company-specific statuses configured in the flexible status system. "
                "Statuses marked with show_in_kanban=False are excluded."
)
class KanbanApplicationsView(RecruiterMixin, APIView):
    """
    Kanban board view for job applications.

    Returns applications grouped by status with pagination per column.
    Designed for efficient Kanban board rendering with drag-and-drop support.

    Features:
    - Uses company-specific statuses from ApplicationStatusModel
    - Groups applications by all active statuses
    - Respects show_in_kanban flag on statuses
    - Paginated results per column (default: 20 items)
    - Ordered by kanban_position within each column
    - Supports custom statuses added by recruiters
    - Optimized queries with prefetching
    """

    permission_classes = [IsAuthenticated]

    def get_language(self) -> str:
        """Extract language from Accept-Language header."""
        accept_language = self.request.headers.get("Accept-Language", "en")
        language = accept_language.split(",")[0].split("-")[0].lower().strip()
        valid_languages = ["en", "ru", "uz"]
        return language if language in valid_languages else "en"

    def _get_company_statuses(self, all_statuses, language):
        """
        Get company's kanban statuses with localized labels.

        Returns a list of status dictionaries ordered by position,
        with statuses hidden from kanban excluded.

        Takes the already-fetched ``all_statuses`` (all active statuses for
        the company) and filters in Python instead of running a second,
        near-identical query — the summary-map service needs that same
        active-statuses set too, so it's fetched once and shared.
        """
        from apps.applications.models import StatusCategory

        statuses = [
            status for status in all_statuses
            if status.show_in_kanban and status.category.key != StatusCategory.WITHDRAWN
        ]

        if statuses:
            return [
                {
                    'key': status.key,
                    'label': status.get_localized_label(language),
                    'color': status.color,
                    'category': status.category.key,
                    'is_terminal': status.category.is_terminal,
                }
                for status in statuses
            ]

        translations = ApplicationStatus.get_translations()
        return [
            {
                'key': choice.value,
                'label': translations.get(choice, {}).get(language, choice.label),
                'color': '#6B7280',
                'category': choice.value,
                'is_terminal': choice in [
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.OFFER_ACCEPTED,
                    ApplicationStatus.OFFER_REJECTED,
                ],
            }
            for choice in ApplicationStatus
            if choice not in (ApplicationStatus.WITHDRAWN, ApplicationStatus.AI_FAILED)
        ]

    def _get_demo_statuses(self, language):
        """
        Returns a fixed subset of standard ApplicationStatus choices to use as
        kanban columns when the company is not yet approved (demo mode).
        Demo applications are stored with these standard status values.
        """
        demo_status_keys = [
            ApplicationStatus.APPLIED,
            ApplicationStatus.INTERVIEW_SCHEDULED,
            ApplicationStatus.INTERVIEWED,
            ApplicationStatus.OFFERED,
            ApplicationStatus.REJECTED,
        ]
        translations = ApplicationStatus.get_translations()
        return [
            {
                'key': choice.value,
                'label': translations.get(choice, {}).get(language, choice.label),
                'color': '#6B7280',
                'category': choice.value,
                'is_terminal': choice in (
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.OFFER_ACCEPTED,
                    ApplicationStatus.OFFER_REJECTED,
                ),
            }
            for choice in demo_status_keys
        ]

    def get(self, request, *args, **kwargs):
        """
        Get Kanban board data with applications grouped by status.
        """

        try:
            page_size = int(request.query_params.get("page_size", 20))
            page = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            page_size = 20
            page = 1

        page_size = max(1, min(page_size, 100))
        page = max(1, page)

        vacancy_id = request.query_params.get("vacancy_id")
        salary_min = request.query_params.get("salary_min")
        salary_max = request.query_params.get("salary_max")
        currency = request.query_params.get("currency")
        recruiter_id = request.query_params.get("recruiter_id")
        applied_from = request.query_params.get("applied_from")
        applied_to = request.query_params.get("applied_to")
        skills = request.query_params.get("skills")
        search = request.query_params.get("search")

        ALLOWED_CURRENCIES = {"UZS", "USD", "EUR", "RUB"}
        if currency:
            currency = currency.upper().strip()
            if currency not in ALLOWED_CURRENCIES:
                raise ValidationError(
                    f"Invalid currency. Allowed values: {', '.join(sorted(ALLOWED_CURRENCIES))}"
                )

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

        recruiter = self.get_recruiter()
        company = recruiter.company
        is_demo_mode = not company.is_active

        if is_demo_mode:
            from apps.vacancies.services.demo_data import get_demo_kanban_response
            language = self.get_language()
            return Response(get_demo_kanban_response(language, page_size, page))

        filters = Q(vacancy__company=company, is_demo=False)

        if vacancy_id:
            try:
                uuid.UUID(str(vacancy_id))
                filters &= Q(vacancy__id=vacancy_id)
            except (ValueError, TypeError):
                raise ValidationError(_("Invalid vacancy_id format. Expected a valid UUID."))

        if recruiter_id:
            try:
                uuid.UUID(str(recruiter_id))
                filters &= Q(vacancy__created_by__id=recruiter_id)
            except (ValueError, TypeError):
                raise ValidationError(_("Invalid recruiter_id format. Expected a valid UUID."))

        if applied_from:
            try:
                from_date = datetime.strptime(applied_from, "%Y-%m-%d").date()
                filters &= Q(applied_at__date__gte=from_date)
            except ValueError:
                raise ValidationError(_("Invalid applied_from format. Use YYYY-MM-DD."))

        if applied_to:
            try:
                to_date = datetime.strptime(applied_to, "%Y-%m-%d").date()
                filters &= Q(applied_at__date__lte=to_date)
            except ValueError:
                raise ValidationError(_("Invalid applied_to format. Use YYYY-MM-DD."))

        if skills:
            skills_list = [skill.strip() for skill in skills.split(",") if skill.strip()]
            if skills_list:
                candidate_ids_with_skills = get_candidate_ids_by_skills(skills_list, company)

                if candidate_ids_with_skills:
                    filters &= Q(candidate__id__in=candidate_ids_with_skills)
                else:
                    filters &= Q(id__in=[])

        if search:
            search_terms = search.strip().split()
            search_q = Q()
            for term in search_terms:
                term_q = Q(
                    Q(candidate__candidateprofile__full_name__icontains=term) |
                    Q(resume_used__title__icontains=term)
                )
                search_q &= term_q
            filters &= search_q

        from apps.applications.models import ApplicationStatusModel

        language = self.get_language()
        # Fetched once and shared with the summary-map service below, which
        # would otherwise run this same company/is_active query a second time.
        all_statuses = list(
            ApplicationStatusModel.objects.filter(
                company=company,
                is_active=True,
            ).select_related('category').order_by('position')
        )
        company_statuses = self._get_company_statuses(all_statuses, language)
        status_label_map = {s['key']: s['label'] for s in company_statuses}

        filtered_queryset = JobApplication.objects.filter(filters)

        if salary_min or salary_max:
            from utils.currency_converter import filter_applications_by_resume_salary
            filtered_queryset = filter_applications_by_resume_salary(
                filtered_queryset, salary_min, salary_max, currency
            )

        from django.db.models import Prefetch
        from apps.resumes.models import Resume

        all_applications = list(
            filtered_queryset.select_related(
                'candidate',
                'candidate__candidateprofile',
                'vacancy',
                'vacancy__company',
                'vacancy__created_by',
                'resume_used',
                'ai_evaluation',
            ).prefetch_related(
                'vacancy__vacancyskill_set__skill',
                Prefetch(
                    'candidate__resumes',
                    queryset=Resume.objects.filter(
                        is_main=True
                    ).prefetch_related('resume_skills__skill'),
                    to_attr='prefetched_main_resumes',
                ),
            ).order_by('kanban_position')
        )

        recruiter_ids = {
            app.vacancy.created_by_id
            for app in all_applications
            if app.vacancy.created_by_id
        }
        assignee_map = {}
        if recruiter_ids:
            from apps.profiles.models import RecruiterProfile
            profiles = RecruiterProfile.objects.filter(
                recruiter_id__in=recruiter_ids
            ).values('recruiter_id', 'full_name')
            assignee_map = {p['recruiter_id']: p['full_name'] for p in profiles}

        applications_by_status = defaultdict(list)
        for app in all_applications:
            applications_by_status[app.status].append(app)

        offset = (page - 1) * page_size

        columns = []

        for status_info in company_statuses:
            status_key = status_info['key']
            status_label = status_info['label']
            status_color = status_info.get('color', '#6B7280')

            status_apps = applications_by_status.get(status_key, [])
            total_count = len(status_apps)

            paginated_apps = status_apps[offset:offset + page_size]

            serializer = KanbanApplicationSerializer(
                paginated_apps,
                many=True,
                context={
                    "request": request,
                    "assignee_map": assignee_map,
                    "status_labels": status_label_map,
                }
            )

            columns.append({
                "key": status_key,
                "label": status_label,
                "color": status_color,
                "count": total_count,
                "applications": serializer.data,
                "has_more": total_count > (offset + page_size),
            })

        return Response({
            "columns": columns,
            "page_size": page_size,
            "page": page,
            "is_demo": False,
        })


kanban_view = KanbanApplicationsView.as_view()
