"""
Subscription views.

API endpoints:
- GET  /subscriptions/plans/         → List plans for the current user's type
- GET  /subscriptions/my/            → Get current user's active subscription
- GET  /subscriptions/seats/         → List seat assignments (company admin only)
- POST /subscriptions/seats/assign/  → Assign a seat (company admin only)
- POST /subscriptions/seats/revoke/  → Revoke a seat (company admin only)
"""

from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, inline_serializer

from core.responses import APIResponse

from apps.authentication.models import Recruiter
from apps.subscriptions.models import (
    SubscriptionPlan,
    CompanySubscription,
    CandidateSubscription,
    SubscriptionSeatAssignment,
)
from apps.subscriptions.serializers import (
    SubscriptionPlanSerializer,
    CompanySubscriptionSerializer,
    CandidateSubscriptionSerializer,
    SeatAssignmentSerializer,
    AssignSeatSerializer,
    RevokeSeatSerializer,
)
from apps.subscriptions.services import SubscriptionService
from utils.recruiter_permission import IsAdminRecruiter


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _resolve_recruiter_with_company(user):
    """
    Fetch the Recruiter instance (with company) for the given user.

    Returns None if the user is not found as a Recruiter.
    Called from view.initial() so it runs exactly once per request.
    """
    try:
        return Recruiter.objects.select_related("company").get(pk=user.id)
    except Recruiter.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────
# Plan listing
# ─────────────────────────────────────────────────────────────────

@extend_schema_view(
    get=extend_schema(
        summary="List subscription plans",
        description="Get available subscription plans filtered by user type. "
                    "Candidates see candidate plans. Recruiters see company plans.",
        responses={
            200: OpenApiResponse(
                response=SubscriptionPlanSerializer(many=True),
                description="List of available plans with features",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
)
class SubscriptionPlanListView(generics.ListAPIView):
    """
    List available subscription plans filtered by the requesting user's type.

    - Recruiter  → company plans only
    - Candidate  → candidate plans only
    """

    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = SubscriptionPlan.objects.filter(is_active=True).prefetch_related(
            "plan_features__feature",
        )
        user = self.request.user
        if getattr(user, "is_recruiter", False):
            queryset = queryset.filter(plan_type=SubscriptionPlan.PlanType.COMPANY)
        elif getattr(user, "is_candidate", False):
            queryset = queryset.filter(plan_type=SubscriptionPlan.PlanType.CANDIDATE)
        else:
            # For users who are neither recruiter nor candidate (e.g., admin users
            # without these flags), return an empty queryset to avoid exposing all
            # plans by default and keep behavior explicit.
            queryset = SubscriptionPlan.objects.none()
        return queryset


# ─────────────────────────────────────────────────────────────────
# Current user's subscription
# ─────────────────────────────────────────────────────────────────

class MySubscriptionView(APIView):
    """
    Get the current user's active subscription.

    - Recruiters → returns the company's active subscription with seat usage.
    - Candidates → returns their active subscription.

    Returns 404 if no active subscription exists.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get my subscription",
        description="Get the currently authenticated user's active subscription. "
                    "Candidates get their CandidateSubscription. "
                    "Recruiters get their CompanySubscription with seat usage.",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "MySubscriptionResponse",
                    fields={
                        "subscription": serializers.JSONField(
                            help_text="CompanySubscriptionSerializer or CandidateSubscriptionSerializer output",
                        ),
                    },
                ),
                description="Active subscription details",
            ),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="No active subscription found"),
        },
    )
    def get(self, request, *args, **kwargs):
        user = request.user

        if getattr(user, "is_recruiter", False):
            return self._recruiter_subscription(request, user)

        if getattr(user, "is_candidate", False):
            return self._candidate_subscription(request, user)

        return APIResponse.bad_request(
            message=_("Unable to determine user type."),
        )

    def _recruiter_subscription(self, request, user):
        recruiter = _resolve_recruiter_with_company(user)
        if recruiter is None or recruiter.company is None:
            return APIResponse.not_found(
                message=_("No company associated with this recruiter."),
            )

        # Fetch subscription with plan features prefetched to avoid N+1
        # when CompanySubscriptionSerializer renders the nested plan.
        subscription = (
            CompanySubscription.objects
            .filter(company=recruiter.company, status=CompanySubscription.Status.ACTIVE)
            .select_related("plan")
            .prefetch_related("seat_assignments", "plan__plan_features__feature")
            .order_by("-created_at")
            .first()
        )
        if subscription is None:
            return APIResponse.not_found(
                message=_("No active subscription found for your company."),
            )

        serializer = CompanySubscriptionSerializer(
            subscription, context={"request": request}
        )
        return APIResponse.success(data=serializer.data)

    def _candidate_subscription(self, request, user):
        from apps.authentication.models import Candidate

        try:
            candidate = Candidate.objects.get(pk=user.id)
        except Candidate.DoesNotExist:
            return APIResponse.not_found(
                message=_("Candidate profile not found."),
            )

        subscription = (
            CandidateSubscription.objects
            .filter(candidate=candidate, status=CandidateSubscription.Status.ACTIVE)
            .select_related("plan")
            .prefetch_related("plan__plan_features__feature")
            .order_by("-created_at")
            .first()
        )
        if subscription is None:
            return APIResponse.not_found(
                message=_("No active subscription found."),
            )

        serializer = CandidateSubscriptionSerializer(
            subscription, context={"request": request}
        )
        return APIResponse.success(data=serializer.data)


# ─────────────────────────────────────────────────────────────────
# Seat management
# ─────────────────────────────────────────────────────────────────

class SeatAssignmentListView(generics.ListAPIView):
    """
    List active seat assignments for the company's current subscription.
    Only accessible by company admins.

    The recruiter + subscription resolution happens in initial() which DRF
    calls exactly once per request (after authentication and permission checks).
    This guarantees that get_queryset() — which may be called multiple times
    by the paginator — never triggers duplicate database queries.
    """

    serializer_class = SeatAssignmentSerializer
    permission_classes = [IsAdminRecruiter]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        recruiter = _resolve_recruiter_with_company(request.user)
        company = recruiter.company if recruiter else None
        self._subscription = CompanySubscription.get_active(company) if company else None

    def get_queryset(self):
        if self._subscription is None:
            return SubscriptionSeatAssignment.objects.none()
        return (
            self._subscription.seat_assignments
            .select_related("recruiter")
            .filter(is_active=True)
            .order_by("seat_type", "created_at")
        )


class AssignSeatView(APIView):
    """
    Assign a seat to a recruiter within the company's active subscription.
    Only accessible by company admins.

    Request body:
    - recruiter_id: UUID of the recruiter (must belong to the same company)
    - seat_type: 'admin' or 'recruiter'

    The recruiter is resolved once by the serializer's PrimaryKeyRelatedField.
    The admin's company is resolved once in initial() and passed to the
    serializer context so the ownership check actually works.
    """

    permission_classes = [IsAdminRecruiter]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        recruiter = _resolve_recruiter_with_company(request.user)
        self._admin_company = recruiter.company if recruiter else None
        self._subscription = (
            CompanySubscription.get_active(self._admin_company)
            if self._admin_company
            else None
        )

    def post(self, request, *args, **kwargs):
        if self._admin_company is None:
            return APIResponse.bad_request(
                message=_("No company associated with this recruiter."),
            )
        if self._subscription is None:
            return APIResponse.bad_request(
                message=_("No active subscription found for your company."),
            )

        serializer = AssignSeatSerializer(
            data=request.data,
            context={"request": request, "admin_company": self._admin_company},
        )
        serializer.is_valid(raise_exception=True)

        # recruiter_id is the Recruiter instance (resolved by PrimaryKeyRelatedField)
        recruiter = serializer.validated_data["recruiter_id"]
        seat_type = serializer.validated_data["seat_type"]

        assignment, error = SubscriptionService.assign_seat(
            self._subscription, recruiter, seat_type
        )
        if error:
            return APIResponse.bad_request(message=error)

        return APIResponse.created(
            data=SeatAssignmentSerializer(assignment).data,
            message=_("Seat assigned successfully."),
        )


class RevokeSeatView(APIView):
    """
    Revoke a recruiter's active seat assignment.
    Only accessible by company admins.

    Request body:
    - recruiter_id: UUID of the recruiter whose seat to revoke
    """

    permission_classes = [IsAdminRecruiter]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        recruiter = _resolve_recruiter_with_company(request.user)
        self._admin_company = recruiter.company if recruiter else None
        self._subscription = (
            CompanySubscription.get_active(self._admin_company)
            if self._admin_company
            else None
        )

    def post(self, request, *args, **kwargs):
        if self._admin_company is None:
            return APIResponse.bad_request(
                message=_("No company associated with this recruiter."),
            )
        if self._subscription is None:
            return APIResponse.bad_request(
                message=_("No active subscription found for your company."),
            )

        serializer = RevokeSeatSerializer(
            data=request.data,
            context={"request": request, "admin_company": self._admin_company},
        )
        serializer.is_valid(raise_exception=True)

        # recruiter_id is the Recruiter instance (resolved by PrimaryKeyRelatedField)
        recruiter = serializer.validated_data["recruiter_id"]
        success, error = SubscriptionService.revoke_seat(self._subscription, recruiter)
        if not success:
            return APIResponse.bad_request(message=error)

        return APIResponse.success(message=_("Seat revoked successfully."))


# ─────────────────────────────────────────────────────────────────
# View instances for URL configuration
# ─────────────────────────────────────────────────────────────────

plan_list_view = SubscriptionPlanListView.as_view()
my_subscription_view = MySubscriptionView.as_view()
seat_assignment_list_view = SeatAssignmentListView.as_view()
assign_seat_view = AssignSeatView.as_view()
revoke_seat_view = RevokeSeatView.as_view()
