from rest_framework import serializers
from django.utils.translation import gettext as _

from apps.authentication.models import Recruiter
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
    CandidateSubscription,
    SubscriptionSeatAssignment,
)
from apps.subscriptions.services import SubscriptionService


class SubscriptionFeatureSerializer(serializers.ModelSerializer):
    """Serializer for subscription features (read-only)."""

    class Meta:
        model = SubscriptionFeature
        fields = ("id", "code", "name", "description", "feature_type")
        read_only_fields = fields


class PlanFeatureSerializer(serializers.ModelSerializer):
    """Serializer for plan-feature links with nested feature detail."""

    feature = SubscriptionFeatureSerializer(read_only=True)

    class Meta:
        model = PlanFeature
        fields = ("feature", "is_enabled", "configuration")
        read_only_fields = fields


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for listing subscription plans.
    Includes the features available in each plan.
    """

    features_detail = PlanFeatureSerializer(
        source="plan_features",
        many=True,
        read_only=True,
        help_text="Features included in this plan with their configuration",
    )

    class Meta:
        model = SubscriptionPlan
        fields = (
            "id",
            "name",
            "slug",
            "plan_type",
            "description",
            "max_admins",
            "max_recruiters",
            "price",
            "billing_period",
            "display_order",
            "features_detail",
        )
        read_only_fields = fields


class CompanySubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for company subscription details.
    Includes plan info and current seat usage.

    seat_usage is computed via a single aggregate query (not two separate COUNTs).
    The subscription passed here must have ``plan__plan_features__feature``
    prefetched to avoid N+1 queries on the nested plan serializer field.

    If serialising a list of subscriptions, also prefetch ``seat_assignments``
    so :py:meth:`get_seat_usage` does not trigger an extra query per object.
    """

    plan = SubscriptionPlanSerializer(read_only=True)
    seat_usage = serializers.SerializerMethodField(
        help_text="Current seat usage vs. limits",
    )

    class Meta:
        model = CompanySubscription
        fields = (
            "id",
            "status",
            "starts_at",
            "expires_at",
            "plan",
            "seat_usage",
            "created_at",
        )
        read_only_fields = fields

    def get_seat_usage(self, obj):
        return SubscriptionService.get_seat_usage(obj)


class CandidateSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for candidate subscription details."""

    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = CandidateSubscription
        fields = (
            "id",
            "status",
            "starts_at",
            "expires_at",
            "plan",
            "created_at",
        )
        read_only_fields = fields


class SeatAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for listing seat assignments."""

    recruiter_email = serializers.CharField(
        source="recruiter.email",
        read_only=True,
    )
    recruiter_id = serializers.UUIDField(
        source="recruiter.id",
        read_only=True,
    )

    class Meta:
        model = SubscriptionSeatAssignment
        fields = (
            "id",
            "recruiter_id",
            "recruiter_email",
            "seat_type",
            "is_active",
            "created_at",
        )
        read_only_fields = fields


class AssignSeatSerializer(serializers.Serializer):
    """
    Serializer for assigning a seat to a recruiter.

    `recruiter_id` is a PrimaryKeyRelatedField so the recruiter is fetched
    and validated in a single query. The view receives the Recruiter instance
    directly from validated_data — no second lookup needed.

    The view must pass `admin_company` in the serializer context so the
    company ownership check works correctly. Relying on `request.user.company`
    does not work because `request.user` is a CustomUser instance (not Recruiter).
    """

    recruiter_id = serializers.PrimaryKeyRelatedField(
        queryset=Recruiter.objects.select_related("company"),
        help_text="ID of the recruiter to assign the seat to",
    )
    seat_type = serializers.ChoiceField(
        choices=SubscriptionSeatAssignment.SeatType.choices,
        help_text="Type of seat to assign (admin or recruiter)",
    )

    def validate_recruiter_id(self, recruiter):
        """
        Ensure the recruiter belongs to the requesting admin's company.
        Uses `admin_company` from context (set by the view in initial())
        rather than request.user.company which would always be None.
        """
        admin_company = self.context.get("admin_company")
        if admin_company and recruiter.company_id != admin_company.id:
            raise serializers.ValidationError(
                _("This recruiter does not belong to your company.")
            )
        return recruiter


class RevokeSeatSerializer(serializers.Serializer):
    """
    Serializer for revoking a recruiter's seat.

    `recruiter_id` is a PrimaryKeyRelatedField so validation and the DB lookup
    happen once. The view receives the Recruiter instance directly.

    Validates that the recruiter belongs to the admin's company.
    """

    recruiter_id = serializers.PrimaryKeyRelatedField(
        queryset=Recruiter.objects.select_related("company"),
        help_text="ID of the recruiter whose seat to revoke",
    )

    def validate_recruiter_id(self, recruiter):
        admin_company = self.context.get("admin_company")
        if admin_company and recruiter.company_id != admin_company.id:
            raise serializers.ValidationError(
                _("This recruiter does not belong to your company.")
            )
        return recruiter


__all__ = [
    "SubscriptionFeatureSerializer",
    "PlanFeatureSerializer",
    "SubscriptionPlanSerializer",
    "CompanySubscriptionSerializer",
    "CandidateSubscriptionSerializer",
    "SeatAssignmentSerializer",
    "AssignSeatSerializer",
    "RevokeSeatSerializer",
]
