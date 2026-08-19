import logging
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Prefetch, Exists, OuterRef
from django.utils.translation import gettext as _

from rest_framework import generics

from core.responses import APIResponse

from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.resumes.models import Resume, ResumeExperience
from apps.resumes.models.choices import WorkStatus
from apps.resumes.services.experience import calculate_total_experience_months
from apps.vacancies.models import Vacancy
from apps.hr_templates.constants import render_template_variables
from apps.conversations.serializers import (
    HeadhuntingCandidateSerializer,
    HeadhuntingInvitationSerializer,
)
from apps.conversations.models import Conversation, Message, MessageType
from apps.conversations.realtime import broadcast_message
from apps.authentication.models import Candidate, Recruiter
from apps.applications.models import JobApplication
from apps.general.services.analytics.status_helpers import get_hired_status_keys

from utils.recruiter_permission import IsRecruiterPermission
from apps.subscriptions.permissions import (
    HasHeadhuntingAccess,
    get_cached_recruiter,
    set_cached_recruiter,
)

logger = logging.getLogger(__name__)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Search by candidate name or position",
        ),
        OpenApiParameter(
            name="salary_min",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Minimum salary filter",
        ),
        OpenApiParameter(
            name="salary_max",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Maximum salary filter",
        ),
        OpenApiParameter(
            name="currency",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Currency for salary filter (USD, UZS, EUR, RUB). Defaults to UZS.",
        ),
        OpenApiParameter(
            name="experience",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Minimum years of experience",
        ),
        OpenApiParameter(
            name="work_status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Work status filter (ACTIVELY_LOOKING, OPEN_TO_OPPORTUNITIES, NOT_LOOKING, PART_TIME_CONSIDERING)",
            enum=[
                WorkStatus.ACTIVELY_LOOKING,
                WorkStatus.OPEN_TO_OPPORTUNITIES,
                WorkStatus.NOT_LOOKING,
                WorkStatus.PART_TIME_CONSIDERING,
            ],
        ),
        OpenApiParameter(
            name="vacancy_id",
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description=_(
                "Optional vacancy UUID to find matching candidates using embedding similarity. "
                "When provided, candidates are filtered and sorted by how well their resume "
                "matches the vacancy requirements. The vacancy must be active and belong to "
                "your company."
            ),
        ),
        OpenApiParameter(
            name="edupartner_ids",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description=_(
                "Comma-separated list of EduPartner (university) UUIDs. "
                "When provided, only candidates associated with one of these "
                "educational partners are returned."
            ),
        ),
    ],
    description=_("List candidates for headhunting with various filters."),
)
class HeadhuntingCandidateListView(generics.ListAPIView):
    """
    API endpoint for recruiters to search and find candidates for headhunting.
    
    Requires the 'headhunting_access' subscription feature (Basic or Pro plan).
    
    Filters available:
    - search: Search by candidate name or position
    - salary_min/salary_max: Filter by salary range
    - experience: Minimum years of experience
    - work_status: Filter by work status (ACTIVELY_LOOKING, OPEN_TO_OPPORTUNITIES, etc.)
    - vacancy_id: Find candidates matching a specific vacancy using embedding similarity
    
    Excludes:
    - Candidates already invited by this recruiter (headhunting conversations exist for this recruiter
    - Candidates hired by this company (OFFER_ACCEPTED applications exist)
    - Only shows candidates with job-seeking work statuses (4 specific statuses)
    
    Returns active resumes with candidate information, optimized to avoid N+1 queries.
    When vacancy_id is provided, results are sorted by similarity score (highest first).
    """

    serializer_class = HeadhuntingCandidateSerializer
    permission_classes = [IsRecruiterPermission, HasHeadhuntingAccess]

    def _build_pagination_meta(self):
        """
        Build pagination metadata in the same shape for standardized responses.
        """
        if not self.paginator:
            return None

        limit = self.paginator.get_limit(self.request)
        if limit is None:
            limit = self.paginator.default_limit

        offset = self.paginator.get_offset(self.request)
        if offset is None:
            offset = 0

        current_page = (offset // limit) + 1 if limit > 0 else 1
        next_page = current_page + 1 if (offset + limit) < self.paginator.count else None
        previous_page = current_page - 1 if current_page > 1 else None

        pagination = {
            "count": self.paginator.count,
            "next": next_page,
            "previous": previous_page,
        }

        if hasattr(self.paginator, "get_limit"):
            pagination["limit"] = limit
        if hasattr(self.paginator, "get_offset"):
            pagination["offset"] = offset

        return pagination

    def _get_recruiter(self):
        """
        Get the recruiter for the current request, using cache when available.
        Returns tuple of (recruiter, company) or (None, None) if not found.
        """
        recruiter = get_cached_recruiter(self.request)
        if recruiter is None:
            try:
                recruiter = Recruiter.objects.select_related('company').get(id=self.request.user.id)
                set_cached_recruiter(self.request, recruiter)
            except Recruiter.DoesNotExist:
                return None, None
        return recruiter, recruiter.company

    def _get_vacancy_for_matching(self, recruiter, company):
        """
        Validate and return vacancy for matching if vacancy_id is provided.
        
        Returns:
            tuple: (vacancy, error_response) where:
                - vacancy is the Vacancy instance or None if not provided
                - error_response is an APIResponse if validation failed, None otherwise
        """
        vacancy_id = self.request.query_params.get('vacancy_id')
        if not vacancy_id:
            return None, None

        # Validate UUID format early to avoid unhandled ORM conversion errors.
        try:
            vacancy_uuid = UUID(str(vacancy_id))
        except (ValueError, TypeError, AttributeError):
            return None, APIResponse.bad_request(
                message=_("Invalid vacancy_id format. Expected UUID")
            )

        try:
            vacancy = Vacancy.objects.get(id=vacancy_uuid)
        except (Vacancy.DoesNotExist, ValidationError, ValueError):
            return None, APIResponse.not_found(
                message=_("Vacancy not found"),
                resource=_("Vacancy")
            )

        if vacancy.company_id != company.id:
            return None, APIResponse.forbidden(
                message=_("This vacancy does not belong to your company")
            )

        if not vacancy.is_active:
            return None, APIResponse.bad_request(
                message=_("Cannot use inactive vacancy for candidate matching")
            )

        return vacancy, None

    def _apply_vacancy_matching_filter(self, queryset, vacancy):
        """
        Apply vacancy-based matching filter using embedding similarity.
        
        Args:
            queryset: The pre-filtered resume queryset
            vacancy: The Vacancy instance to match against
            
        Returns:
            tuple: (filtered_queryset, similarity_map) where:
                - filtered_queryset is the queryset limited to matching resumes
                - similarity_map is a dict of {candidate_id: similarity_score}
        """
        from apps.matching.services.matching import VacancyMatcher

        # Use fixed values for matching - pagination handles result count
        min_similarity = 0.3
        top_k = 500  # Large enough to let pagination control the result count

        try:
            matching_resumes = VacancyMatcher.find_matching_resumes(
                vacancy=vacancy,
                top_k=top_k,
                min_similarity=min_similarity
            )

            if not matching_resumes:
                return queryset.none(), {}

            # Aggregate at candidate level to align with base queryset,
            # which returns one resume per candidate via distinct('candidate_id').
            similarity_map = {}
            for resume in matching_resumes:
                candidate_id = str(resume.candidate_id)
                similarity_score = resume.similarity_score
                current_score = similarity_map.get(candidate_id)
                if current_score is None or similarity_score > current_score:
                    similarity_map[candidate_id] = similarity_score

            matched_candidate_ids = list(similarity_map.keys())

            return queryset.filter(candidate_id__in=matched_candidate_ids), similarity_map

        except ValueError as e:
            # Vacancy has no embedding yet
            logger.warning(
                _("Vacancy matching skipped - vacancy %(vacancy_id)s has no embedding: %(error)s") % {
                    "vacancy_id": vacancy.id,
                    "error": str(e)
                }
            )
            return queryset, {}
        except Exception as e:
            # Unexpected error - log and fallback to unfiltered queryset
            logger.error(
                _("Vacancy matching failed for vacancy %(vacancy_id)s: %(error)s") % {
                    "vacancy_id": vacancy.id,
                    "error": str(e)
                },
                exc_info=True
            )
            return queryset, {}

    def get_queryset(self):
        """
        Get queryset of candidates for headhunting, applying filters and exclusions.
        Optimized to minimize database hits and handle experience filtering in Python
        """
        recruiter, company = self._get_recruiter()
        if recruiter is None:
            return Resume.objects.none()

        # Subqueries to exclude candidates already invited by this recruiter or hired by this company
        invited_by_recruiter = Conversation.objects.filter(
            candidate_id=OuterRef('candidate_id'),
            recruiter_id=recruiter.id,
            application__isnull=True,  # Headhunting conversations only
        )

        # Subquery to check if candidate has been hired by this company
        # Check all vacancies belonging to this company
        # Uses category-based lookup to support custom "hired" statuses
        hired_status_keys = get_hired_status_keys(company.id)
        hired_by_company = JobApplication.objects.filter(
            candidate_id=OuterRef('candidate_id'),
            vacancy__company=company,
            status__in=hired_status_keys,
        )

        queryset = (
            Resume.objects
            .filter(
                is_active=True,
                # Only show candidates with job-seeking work statuses
                work_status__in=[
                    WorkStatus.ACTIVELY_LOOKING,
                    WorkStatus.OPEN_TO_OPPORTUNITIES,
                    WorkStatus.NOT_LOOKING,
                    WorkStatus.PART_TIME_CONSIDERING,
                ],
            )
            .exclude(Exists(invited_by_recruiter))
            .exclude(Exists(hired_by_company))
            .select_related(
                'candidate',
                'candidate__candidateprofile',
                'candidate__edupartner',
            )
            .prefetch_related(
                Prefetch(
                    'experiences',
                    queryset=ResumeExperience.objects.only('id', 'resume_id', 'start_date', 'end_date'),
                    to_attr='prefetched_experiences',
                ),
            )
            .order_by('candidate_id', '-is_main', '-created_at')
            .distinct('candidate_id')
        )

        # Apply filters in Python to handle complex experience calculation and avoid multiple DB hits.
        queryset = self._apply_search_filter(queryset)
        queryset = self._apply_salary_filter(queryset)
        queryset = self._apply_work_status_filter(queryset)
        queryset = self._apply_edupartner_filter(queryset)

        # Experience filter applied last — operates on already-filtered queryset
        queryset = self._apply_experience_filter(queryset)

        return queryset

    def list(self, request, *args, **kwargs):
        """
        Override list to handle vacancy matching with similarity-based sorting.
        When vacancy_id is provided, results are sorted by similarity score (highest first).
        """
        recruiter, company = self._get_recruiter()
        if recruiter is None:
            return APIResponse.forbidden(
                message=_("Authenticated user is not a recruiter")
            )

        # Check for vacancy matching
        vacancy, error_response = self._get_vacancy_for_matching(recruiter, company)
        if error_response:
            return error_response

        queryset = self.filter_queryset(self.get_queryset())

        if vacancy:
            # Apply vacancy matching filter
            queryset, similarity_map = self._apply_vacancy_matching_filter(queryset, vacancy)

            if similarity_map:
                # Convert to list and sort by similarity score
                result_list = list(queryset)
                for resume in result_list:
                    resume.similarity_score = similarity_map.get(str(resume.candidate_id))
                result_list.sort(
                    key=lambda r: similarity_map.get(str(r.candidate_id), 0),
                    reverse=True
                )

                # Apply pagination
                page = self.paginate_queryset(result_list)
                if page is not None:
                    serializer = self.get_serializer(page, many=True)
                    return APIResponse.success(
                        data=serializer.data,
                        message=_("Candidates matched and listed successfully"),
                        pagination=self._build_pagination_meta(),
                    )

                serializer = self.get_serializer(result_list, many=True)
                return APIResponse.success(
                    data=serializer.data,
                    message=_("Candidates matched and listed successfully"),
                )

        # Default behavior (no matching or matching returned no results)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return APIResponse.success(
                data=serializer.data,
                message=_("Candidates listed successfully"),
                pagination=self._build_pagination_meta(),
            )

        serializer = self.get_serializer(queryset, many=True)
        return APIResponse.success(
            data=serializer.data,
            message=_("Candidates listed successfully"),
        )

    def _apply_search_filter(self, queryset):
        """
        Apply search filter by candidate name or position.
        """
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(candidate__candidateprofile__full_name__icontains=search) |
                Q(position__icontains=search)
            )
        return queryset

    def _apply_salary_filter(self, queryset):
        """
        Apply salary range filter with currency conversion.
        Uses the currency_converter utility to handle cross-currency comparisons.
        """
        salary_min = self.request.query_params.get('salary_min')
        salary_max = self.request.query_params.get('salary_max')
        currency = self.request.query_params.get('currency')

        if not salary_min and not salary_max:
            return queryset

        from utils.currency_converter import filter_resumes_by_salary
        return filter_resumes_by_salary(queryset, salary_min, salary_max, currency)

    def _apply_experience_filter(self, queryset):
        """
        Apply experience filter by calculating total experience in Python.
        This avoids multiple database hits and complex annotations.
        """
        experience = self.request.query_params.get('experience')
        if not experience:
            return queryset

        try:
            min_years = int(experience)
        except (ValueError, TypeError):
            return queryset

        min_months = min_years * 12
        max_months = (min_years + 1) * 12  # +1 year upper bound

        from collections import defaultdict
        candidate_intervals = defaultdict(list)

        # Force queryset evaluation to trigger the prefetch_related on experiences.
        # This avoids a separate query by reusing the prefetched data.
        evaluated = list(queryset)
        for resume in evaluated:
            prefetched = getattr(resume, 'prefetched_experiences', None)
            if prefetched is None:
                continue
            for exp in prefetched:
                if exp.start_date:
                    candidate_intervals[resume.candidate_id].append((exp.start_date, exp.end_date))

        qualifying_candidate_ids = set()
        for candidate_id, intervals in candidate_intervals.items():
            total_months = calculate_total_experience_months(intervals)
            if min_months <= total_months < max_months:
                qualifying_candidate_ids.add(candidate_id)

        return queryset.filter(candidate_id__in=qualifying_candidate_ids)

    def _apply_work_status_filter(self, queryset):
        """
        Apply work status filter.
        Only allows the 4 job-seeking statuses.
        """
        work_status = self.request.query_params.get('work_status')
        valid_statuses = [
            WorkStatus.ACTIVELY_LOOKING,
            WorkStatus.OPEN_TO_OPPORTUNITIES,
            WorkStatus.NOT_LOOKING,
            WorkStatus.PART_TIME_CONSIDERING,
        ]

        if work_status and work_status in valid_statuses:
            queryset = queryset.filter(work_status=work_status)

        return queryset

    def _apply_edupartner_filter(self, queryset):
        """
        Apply university (EduPartner) filter.
        Accepts a comma-separated list of EduPartner UUIDs via edupartner_ids.
        Applied as a plain filter on the existing queryset — no extra queries.
        """
        edupartner_ids = self.request.query_params.get('edupartner_ids')
        if not edupartner_ids:
            return queryset

        valid_ids = []
        for raw_id in edupartner_ids.split(','):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            try:
                valid_ids.append(UUID(raw_id))
            except (ValueError, TypeError):
                continue

        if not valid_ids:
            return queryset

        return queryset.filter(candidate__edupartner_id__in=valid_ids)


@extend_schema(
    request=HeadhuntingInvitationSerializer,
    description="Send headhunting invitation to selected candidates.",
)
class HeadhuntingInvitationView(generics.CreateAPIView):
    """
    API endpoint for recruiters to send headhunting invitations to candidates.
    
    Requires the 'headhunting_access' subscription feature (Basic or Pro plan).
    
    Creates conversations with candidates and sends the invitation letter.
    Each candidate receives the letter as a message in a new conversation.
    
    Request body:
    - candidate_ids: List of candidate UUIDs to invite (max 50)
    - letter: The invitation letter content
    - vacancy_id: The vacancy to invite candidates for
    """

    serializer_class = HeadhuntingInvitationSerializer
    permission_classes = [IsRecruiterPermission, HasHeadhuntingAccess]

    def _build_message_metadata(self, vacancy_id):
        """
        Build metadata dict for invitation message.
        
        Args:
            vacancy_id: UUID of the vacancy (or None)
            
        Returns:
            dict: Metadata to store with the message
        """
        metadata = {}
        if vacancy_id is not None:
            metadata["vacancy_id"] = str(vacancy_id)
        return metadata

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        candidate_ids = serializer.validated_data['candidate_ids']
        letter = serializer.validated_data['letter']
        vacancy_id = serializer.validated_data.get('vacancy_id')

        # Build message metadata
        message_metadata = self._build_message_metadata(vacancy_id)

        # Reuse recruiter cached by the permission layer
        recruiter = get_cached_recruiter(request)
        if recruiter is None:
            try:
                recruiter = Recruiter.objects.select_related('company').get(id=request.user.id)
                set_cached_recruiter(request, recruiter)
            except Recruiter.DoesNotExist:
                return APIResponse.forbidden(message=_("Authenticated user is not a recruiter."))

        # Use vacancy already resolved by the serializer's validate_vacancy_id
        vacancy = serializer.context.get('validated_vacancy')
        if vacancy is None and vacancy_id:
            try:
                vacancy = Vacancy.objects.get(id=vacancy_id, company=recruiter.company)
            except Vacancy.DoesNotExist:
                return APIResponse.not_found(message=_("Vacancy not found"))

        # Fetch existing conversations with select_for_update to prevent race conditions
        # Keep as QuerySet to maintain locks throughout the transaction
        existing_conversations = (
            Conversation.objects
            .filter(
                recruiter_id=recruiter.id,
                candidate_id__in=candidate_ids,
                application__isnull=True,  # Only headhunting conversations
            )
            .select_for_update()
        )
        # Build lookup map while keeping QuerySet locked
        existing_conv_map = {conv.candidate_id: conv for conv in existing_conversations}

        # Prepare results
        created_conversations = []
        messages_created = []
        skipped_candidates = []

        # Get all candidates at once to avoid N+1
        candidates = Candidate.objects.filter(id__in=candidate_ids).select_related('candidateprofile')
        candidate_map = {c.id: c for c in candidates}

        for candidate_id in candidate_ids:
            candidate = candidate_map.get(candidate_id)
            if not candidate:
                skipped_candidates.append(str(candidate_id))
                continue

            # Render the letter with actual candidate/vacancy/company data
            rendered_letter = render_template_variables(letter, candidate, vacancy, recruiter.company)

            # Check if conversation exists in our pre-fetched map
            if candidate_id in existing_conv_map:
                # Add message to existing conversation
                conversation = existing_conv_map[candidate_id]

                # Update vacancy if provided (headhunting for a new vacancy)
                if vacancy_id and conversation.vacancy_id != vacancy_id:
                    conversation.vacancy_id = vacancy_id
                    conversation.is_read_by_candidate = False
                    conversation.save(update_fields=['vacancy_id', 'is_read_by_candidate', 'updated_at'])
                else:
                    # Mark conversation as unread for candidate
                    conversation.is_read_by_candidate = False
                    conversation.save(update_fields=['is_read_by_candidate', 'updated_at'])

                message = Message.objects.create(
                    conversation=conversation,
                    sender_type="RECRUITER",
                    message_type=MessageType.HUNTING_INVITATION,
                    content=rendered_letter,
                    metadata=message_metadata,
                    is_read=False,
                )
                messages_created.append(message)
            else:
                # Use get_or_create to handle race conditions
                # This ensures only one conversation is created per recruiter-candidate pair
                conversation, created = Conversation.objects.get_or_create(
                    application=None,
                    candidate=candidate,
                    recruiter=recruiter,
                    defaults={
                        'vacancy_id': vacancy_id,
                        'is_read_by_recruiter': True,
                        'is_read_by_candidate': False,
                    }
                )

                # If conversation already existed (created by concurrent request),
                # update the vacancy and mark as unread for candidate
                if not created:
                    update_fields = ['is_read_by_candidate', 'updated_at']
                    conversation.is_read_by_candidate = False
                    if vacancy_id is not None:
                        conversation.vacancy_id = vacancy_id
                        update_fields.append('vacancy_id')
                    conversation.save(update_fields=update_fields)
                else:
                    created_conversations.append(conversation)

                # Create the invitation message
                message = Message.objects.create(
                    conversation=conversation,
                    sender_type="RECRUITER",
                    message_type=MessageType.HUNTING_INVITATION,
                    content=rendered_letter,
                    metadata=message_metadata,
                    is_read=False,
                )
                messages_created.append(message)

        # Invitations are pushed after every conversation in the batch is
        # written, so a candidate with the chat open sees the invitation land
        # without reloading.
        for message in messages_created:
            broadcast_message(message)

        return APIResponse.created(
            data={
                "new_conversations": len(created_conversations),
                "messages_sent": len(messages_created),
                "skipped": skipped_candidates,
            },
            message=_("Invitation sent to %(count)d candidate(s)") % {"count": len(messages_created)},
        )


headhunting_candidate_list_view = HeadhuntingCandidateListView.as_view()
headhunting_invitation_view = HeadhuntingInvitationView.as_view()
