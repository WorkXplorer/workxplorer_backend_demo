import logging

from django.utils.translation import gettext as _
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.skills.localization import user_preferred_language
from apps.student_analytics.models import VacancySkillRoadmap, VacancyRoadmapItem
from apps.student_analytics.serializers.vacancy_roadmap import (
    VacancySkillRoadmapSerializer,
    VacancyRoadmapItemSerializer,
)
from config.pagination import CustomPagination
from core.responses import APIResponse

logger = logging.getLogger(__name__)


class VacancyRoadmapAPIView(APIView):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access vacancy roadmaps."))

        paginator = self.pagination_class()
        roadmaps = VacancySkillRoadmap.objects.filter(
            application__candidate=user,
        ).select_related(
            "application__vacancy__company",
        ).prefetch_related("items__skill").all()

        language = user_preferred_language(user)
        page = paginator.paginate_queryset(roadmaps, request)
        if page is not None:
            serializer = VacancySkillRoadmapSerializer(
                page, many=True, context={"language": language},
            )
            return paginator.get_paginated_response(serializer.data)

        serializer = VacancySkillRoadmapSerializer(
            roadmaps, many=True, context={"language": language},
        )
        return APIResponse.success(data=serializer.data)


class VacancyRoadmapItemDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, item_id, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access roadmap items."))

        try:
            item = VacancyRoadmapItem.objects.select_related(
                "skill", "roadmap__application__vacancy__company",
            ).get(
                id=item_id,
                roadmap__application__candidate=user,
            )
        except (VacancyRoadmapItem.DoesNotExist, ValueError):
            return APIResponse.not_found(message=_("Roadmap item not found."))

        language = user_preferred_language(user)
        ctx = {"language": language}
        serializer = VacancyRoadmapItemSerializer(item, context=ctx)
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


