from datetime import timedelta

from rest_framework import generics
from rest_framework.exceptions import ValidationError, Throttled
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Case, When, IntegerField
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes

from apps.skills.models import Skill
from apps.skills.localization import skill_name_query
from apps.skills.serializers import (
    SkillSerializer,
    SkillCreateSerializer,
)
from core.responses import APIResponse
from utils.candidate_permission import IsCandidateOrRecruiterPermission

# Maximum number of skills a single user may submit within a rolling hour.
MAX_SKILLS_PER_HOUR = getattr(settings, "MAX_SKILLS_CREATED_PER_HOUR", 5)


class SkillListNamesAPIView(generics.ListAPIView):
    """
    API view for listing skills with lightweight response (id and name only).
    Optimized for dropdown/autocomplete functionality with search filtering.

    This endpoint is designed to be called after user types 2+ characters.
    Returns minimal data (only id and name) for better performance.

    Supports:
        - Search filtering by skill name (case-insensitive)
        - Optional category filtering
        - Results limited to 20 items for autocomplete
    """

    # Include pending (is_active=False) skills so any candidate can reuse a
    # skill another candidate submitted; approved skills are ranked first and
    # each result carries an `is_pending` flag so the frontend can warn users.
    queryset = Skill.objects.all().order_by("-is_active", "name")
    serializer_class = SkillSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    @extend_schema(
        summary="Get skill names list (autocomplete)",
        description="Get a lightweight list of skills with only ID and name. Ideal for dropdown/autocomplete with search filtering.",
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Search by skill name (case-insensitive substring match). Recommended: minimum 2 characters",
                required=False,
                examples=[
                    OpenApiExample("Search by 'Py'", value="Py"),
                    OpenApiExample("Search by 'Java'", value="Java"),
                ],
            ),
            OpenApiParameter(
                name="category_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Filter skills by category ID (optional)",
                required=False,
                examples=[
                    OpenApiExample("Programming category", value=1),
                ],
            ),
        ],
        responses={
            200: SkillSerializer(many=True),
        },
        tags=["Skills"],
    )
    def get(self, request, *args, **kwargs):
        """
        Get lightweight list of skills for dropdown/autocomplete.

        Query Parameters:
            - search (str): Filter skills by name containing this string (case-insensitive)
            - category_id (int): Filter skills by category ID (optional)

        Returns:
            - count: Total number of matching skills
            - results: List of skills with id and name only (max 20 items)

        Example:
            GET /api/skills/list-names/?search=Py
            Response: {"count": 2, "results": [{"id": 1, "name": "Python"}, {"id": 2, "name": "PyCharm"}]}

            GET /api/skills/list-names/?search=Java&category_id=1
            Response: {"count": 1, "results": [{"id": 5, "name": "JavaScript"}]}
        """
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        """
        Filter skills by search and category parameters with relevance ordering.
        Prioritizes matches at the beginning of the name.
        Limits results to 20 items for autocomplete performance.
        """
        queryset = super().get_queryset()

        # Search filter by skill name (case-insensitive, must start with search term)
        search = self.request.query_params.get("search", "").strip()
        if search:
            # Filter: only items that start with the search term (case-insensitive)
            queryset = queryset.filter(
                name__istartswith=search
            ) | queryset.filter(
                name_en__istartswith=search
            ) | queryset.filter(
                name_ru__istartswith=search
            ) | queryset.filter(
                name_uz__istartswith=search
            )
            queryset = queryset.distinct()

            # Order by relevance: exact match first, then approved skills, then name
            queryset = queryset.annotate(
                relevance=Case(
                    When(
                        skill_name_query(search), then=1
                    ),  # Exact match gets highest priority
                    default=2,  # Partial matches (startswith) get lower priority
                    output_field=IntegerField(),
                )
            ).order_by("relevance", "-is_active", "name")

        # Category filter (optional)
        category_id = self.request.query_params.get("category_id", "").strip()
        if category_id:
            try:
                category_id = int(category_id)
                queryset = queryset.filter(category__id=category_id)
            except ValueError:
                raise ValidationError(_("Invalid category_id format. Expected an integer."))

        # Limit results for autocomplete (prevent returning too many items)
        # This is applied at Python level after ORM query
        queryset = queryset[:20]

        return queryset


class SkillCreateAPIView(generics.CreateAPIView):
    """
    Let a candidate (or recruiter) submit a new skill.

    The skill is stored immediately with ``is_active=False`` (pending) and is
    only activated once the daily AI validation approves it. A single user may
    submit at most :data:`MAX_SKILLS_PER_HOUR` skills within a rolling hour.
    """

    queryset = Skill.objects.all()
    serializer_class = SkillCreateSerializer
    permission_classes = [IsCandidateOrRecruiterPermission]

    def _lock_user_for_creation(self, user):
        """
        Serialize concurrent skill-creation requests from the same user.

        A Postgres transaction-scoped advisory lock keyed on the user's id
        blocks a second concurrent request until the first one's
        check-then-insert has committed, closing the race in
        ``_enforce_hourly_limit`` where two simultaneous requests could both
        read a count under the limit before either insert lands.

        ``user.id`` is a UUID, not a bigint, so it's hashed down to an int8
        lock key via ``hashtext`` — a rare hash collision between two users
        only causes unnecessary serialization, never an incorrect count.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)", [str(user.id)]
            )

    def _enforce_hourly_limit(self, user):
        """Raise ``Throttled`` if the user exceeded the hourly creation limit."""
        window_start = timezone.now() - timedelta(hours=1)
        recent_qs = Skill.objects.filter(created_by=user, created_at__gte=window_start)
        if recent_qs.count() >= MAX_SKILLS_PER_HOUR:
            oldest_created_at = recent_qs.earliest("created_at").created_at
            retry_after = (oldest_created_at + timedelta(hours=1)) - timezone.now()
            raise Throttled(
                wait=max(int(retry_after.total_seconds()), 1),
                detail=_(
                    "You can create at most %(limit)d skills per hour. "
                    "Please try again later."
                )
                % {"limit": MAX_SKILLS_PER_HOUR},
            )

    def perform_create(self, serializer):
        serializer.save(is_active=False, created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self._lock_user_for_creation(request.user)
            self._enforce_hourly_limit(request.user)
            self.perform_create(serializer)
        return APIResponse.created(
            data=serializer.data,
            message=_("Skill created successfully and is pending approval."),
        )


# Create view instances
skill_list_names_view = SkillListNamesAPIView.as_view()
skill_create_view = SkillCreateAPIView.as_view()
