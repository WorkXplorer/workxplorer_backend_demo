import logging

from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer

from apps.skills.localization import user_preferred_language
from apps.student_analytics.models import SkillRoadmap, RoadmapItem
from apps.student_analytics.serializers import SkillRoadmapSerializer, RoadmapItemSerializer
from apps.student_analytics.services import generate_roadmap
from apps.student_analytics.throttles import AnalyticsRegenerationThrottle
from core.responses import APIResponse

logger = logging.getLogger(__name__)


class RoadmapAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get skill roadmap",
        description="Get the candidate's latest AI-generated skill roadmap. "
                    "Includes skill items with estimated time to learn and priority.",
        responses={
            200: OpenApiResponse(
                response=SkillRoadmapSerializer,
                description="Skill roadmap data",
            ),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="No roadmap found. Generate one first."),
        },
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access roadmaps."))

        roadmap = (
            SkillRoadmap.objects.filter(analytics__candidate=user)
            .prefetch_related("items__skill")
            .order_by("-generated_at")
            .first()
        )
        if not roadmap:
            return APIResponse.not_found(message=_("No roadmap found. Generate one first."))

        language = user_preferred_language(user)
        serializer = SkillRoadmapSerializer(roadmap, context={"language": language})
        return APIResponse.success(data=serializer.data)


class GenerateRoadmapAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnalyticsRegenerationThrottle]

    @extend_schema(
        summary="Generate skill roadmap",
        description="Generate a new AI-powered skill roadmap for the candidate. "
                    "Optionally specify a resume_id and AI model.",
        request=inline_serializer(
            "GenerateRoadmapRequest",
            fields={
                "ai_model": serializers.ChoiceField(
                    choices=[("default", "Default")],
                    default="default",
                    help_text="AI model to use for generation",
                ),
                "resume_id": serializers.UUIDField(
                    required=False,
                    help_text="Resume UUID to base the roadmap on",
                ),
            },
        ),
        responses={
            201: OpenApiResponse(
                response=SkillRoadmapSerializer,
                description="Roadmap generated successfully",
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
            return APIResponse.forbidden(message=_("Only candidates can generate roadmaps."))

        ai_model = request.data.get("ai_model", "default")
        if ai_model not in ("default",):
            return APIResponse.bad_request(message=_("ai_model must be 'default'."))

        resume_id = request.data.get("resume_id")

        try:
            roadmap = generate_roadmap(user, resume_id=resume_id, ai_model=ai_model)
            if roadmap is None:
                return APIResponse.server_error(message=_("Failed to generate roadmap via AI. Please try again."))
        except Exception:
            logger.exception("Failed to generate roadmap")
            return APIResponse.server_error(message=_("Failed to generate roadmap."))

        if not roadmap:
            return APIResponse.not_found(message=_("Resume not found."))

        language = user_preferred_language(user)
        serializer = SkillRoadmapSerializer(roadmap, context={"language": language})
        return APIResponse.created(
            data=serializer.data,
            message=_("Roadmap generated successfully."),
        )


class RoadmapItemDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get roadmap item detail",
        description="Get detailed information about a specific roadmap item, including "
                    "skill details and top 5 learning materials.",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "RoadmapItemDetailResponse",
                    fields={
                        "item": serializers.JSONField(
                            help_text="RoadmapItemSerializer output with learning_materials",
                        ),
                    },
                ),
                description="Roadmap item details with learning materials",
            ),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Roadmap item not found"),
        },
    )
    def get(self, request, item_id, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access roadmap items."))

        try:
            item = RoadmapItem.objects.select_related("skill", "roadmap__analytics").get(
                id=item_id,
                roadmap__analytics__candidate=user,
            )
        except (RoadmapItem.DoesNotExist, ValueError):
            return APIResponse.not_found(message=_("Roadmap item not found."))

        language = user_preferred_language(user)
        ctx = {"language": language}
        serializer = RoadmapItemSerializer(item, context=ctx)
        data = serializer.data

        if item.skill:
            from apps.skills.models import SkillLearningMaterial
            from apps.skills.serializers import SkillLearningMaterialSerializer

            materials = SkillLearningMaterial.objects.filter(
                skill=item.skill,
                material__is_active=True,
            ).select_related("material").order_by("-relevance_score")[:5]

            data["learning_materials"] = SkillLearningMaterialSerializer(
                materials, many=True, context=ctx,
            ).data

        return APIResponse.success(data=data)
