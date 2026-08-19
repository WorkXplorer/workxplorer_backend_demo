import logging
from datetime import datetime, timezone

from django.core.cache import cache
from django.utils.translation import gettext as _
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.skills.localization import user_preferred_language
from apps.student_analytics.models import StudentAnalytics
from apps.student_analytics.serializers import StudentAnalyticsSerializer, UpdateTargetRoleSerializer
from apps.student_analytics.services import compute_or_refresh_analytics
from apps.student_analytics.services.salary_calculator import calculate_salary
from apps.student_analytics.throttles import AnalyticsRegenerationThrottle
from core.responses import APIResponse

logger = logging.getLogger(__name__)


class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get student analytics dashboard",
        description="Get the candidate's analytics dashboard including skills analysis, "
                    "market insights, resume analysis, and target role data. "
                    "Auto-generates analytics if none exist.",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "DashboardResponse",
                    fields={
                        "analytics": serializers.JSONField(
                            help_text="StudentAnalyticsSerializer output",
                        ),
                    },
                ),
                description="Analytics dashboard data",
            ),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Resume not found"),
        },
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access analytics."))

        try:
            analytics = StudentAnalytics.objects.select_related(
                "roadmap"
            ).prefetch_related("roadmap__items__skill").get(candidate=user)
        except StudentAnalytics.DoesNotExist:
            analytics = compute_or_refresh_analytics(user)
            if not analytics:
                return APIResponse.not_found(message=_("Resume not found."))

        language = user_preferred_language(user)
        serializer = StudentAnalyticsSerializer(analytics, context={"language": language})
        return APIResponse.success(data=serializer.data)


class RegenerateAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnalyticsRegenerationThrottle]

    @extend_schema(
        summary="Regenerate analytics",
        description="Regenerate the candidate's analytics using AI. "
                    "Optionally specify a resume_id and AI model.",
        request=inline_serializer(
            "RegenerateAnalyticsRequest",
            fields={
                "ai_model": serializers.ChoiceField(
                    choices=[("default", "Default")],
                    default="default",
                    help_text="AI model to use for generation",
                ),
                "resume_id": serializers.UUIDField(
                    required=False,
                    help_text="Resume UUID to use as base for analytics",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "RegenerateAnalyticsResponse",
                    fields={
                        "analytics": serializers.JSONField(
                            help_text="Updated StudentAnalyticsSerializer output",
                        ),
                    },
                ),
                description="Analytics regenerated successfully",
            ),
            400: OpenApiResponse(description="Invalid ai_model value"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Resume not found"),
            429: OpenApiResponse(description="Too many requests — rate limited"),
        },
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can regenerate analytics."))

        ai_model = request.data.get("ai_model", "default")
        if ai_model not in ("default",):
            return APIResponse.bad_request(message=_("ai_model must be 'default'."))

        resume_id = request.data.get("resume_id")

        try:
            analytics = compute_or_refresh_analytics(user, resume_id=resume_id, ai_model=ai_model)
        except Exception:
            logger.exception("Failed to compute analytics")
            return APIResponse.server_error(message=_("Failed to compute analytics."))

        if not analytics:
            return APIResponse.not_found(message=_("Resume not found."))

        language = user_preferred_language(user)
        serializer = StudentAnalyticsSerializer(analytics, context={"language": language})
        return APIResponse.success(
            data=serializer.data,
            message=_("Analytics regenerated successfully."),
        )


class UpdateTargetRoleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Update target role",
        description="Update the candidate's target role for analytics and salary calculations.",
        request=inline_serializer(
            "UpdateTargetRoleRequest",
            fields={
                "target_role": serializers.CharField(
                    help_text="Desired job title / target role",
                ),
            },
        ),
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "UpdateTargetRoleResponse",
                    fields={
                        "analytics": serializers.JSONField(
                            help_text="Updated StudentAnalyticsSerializer output",
                        ),
                    },
                ),
                description="Target role updated successfully",
            ),
            400: OpenApiResponse(description="target_role is required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Analytics not found. Generate analytics first."),
        },
    )
    def patch(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can update target role."))

        serializer = UpdateTargetRoleSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(field_errors=serializer.errors)

        target_role = serializer.validated_data["target_role"].strip()
        if not target_role:
            return APIResponse.bad_request(message=_("target_role is required."))

        try:
            analytics = StudentAnalytics.objects.get(candidate=user)
        except StudentAnalytics.DoesNotExist:
            return APIResponse.not_found(message=_("Analytics not found. Generate analytics first."))

        analytics.target_role = target_role
        analytics.save(update_fields=["target_role", "updated_at"])

        language = user_preferred_language(user)
        response_serializer = StudentAnalyticsSerializer(analytics, context={"language": language})
        return APIResponse.success(
            data=response_serializer.data,
            message=_("Target role updated successfully."),
        )


class SalaryCalculatorAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        description="Calculate salary based on candidate experience and market data",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "SalaryCalculatorResponse",
                    fields={
                        "current_salary": serializers.CharField(),
                        "potential_salary": serializers.CharField(),
                        "market_median": serializers.CharField(),
                        "match_percentage": serializers.CharField(),
                        "experience_months": serializers.IntegerField(),
                        "sample_count": serializers.IntegerField(),
                        "currency": serializers.CharField(),
                        "sector_reference_salary": serializers.CharField(allow_null=True),
                        "sector_reference_period": serializers.CharField(allow_null=True),
                    },
                ),
                description="Salary calculated successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {
                                "current_salary": "8000000.00",
                                "potential_salary": "12000000.00",
                                "market_median": "10000000.00",
                                "match_percentage": "80.0",
                                "experience_months": 24,
                                "sample_count": 10,
                                "currency": "UZS",
                                "sector_reference_salary": "11500000.00",
                                "sector_reference_period": "2026-Q2",
                            },
                            "timestamp": "2026-06-18T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Analytics not found, target role not set, or insufficient market data",
            ),
            403: OpenApiResponse(
                description="User is not a candidate",
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access salary calculator."))

        # ponytail: per-user daily cache, upgrade to per-candidate if multiple candidates share a user
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cache_key = f"salary_calc_{user.pk}_{today}"
        cached = cache.get(cache_key)
        if cached is not None:
            return APIResponse.success(data=cached)

        try:
            analytics = StudentAnalytics.objects.select_related("resume").prefetch_related(
                "resume__experiences",
            ).get(candidate=user)
        except StudentAnalytics.DoesNotExist:
            return APIResponse.not_found(message=_("Analytics not found. Generate analytics first."))

        target_role = analytics.target_role
        if not target_role:
            return APIResponse.bad_request(message=_("Target role is required. Set it first."))

        result = calculate_salary(user, analytics.resume, target_role)
        if isinstance(result, dict) and result.get("error") == "insufficient_data":
            return APIResponse.not_found(message=_("Insufficient data to calculate salary for this role."))

        cache.set(cache_key, result, timeout=86400)
        return APIResponse.success(data=result)
