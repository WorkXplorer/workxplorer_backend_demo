from django.utils.translation import gettext as _
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.skills.localization import user_preferred_language
from apps.skills.models import Skill, SkillLearningMaterial
from apps.skills.serializers import SkillLearningMaterialSerializer
from core.responses import APIResponse


class SkillLearningMaterialsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, skill_id, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can access learning materials."))

        try:
            skill = Skill.objects.get(id=skill_id, is_active=True)
        except Skill.DoesNotExist:
            return APIResponse.not_found(message=_("Skill not found."))

        materials = SkillLearningMaterial.objects.filter(
            skill=skill,
            material__is_active=True,
        ).select_related("material").order_by("-relevance_score")[:10]

        language = user_preferred_language(user)
        serializer = SkillLearningMaterialSerializer(
            materials,
            many=True,
            context={"language": language},
        )
        return APIResponse.success(data=serializer.data)


skill_learning_materials_view = SkillLearningMaterialsAPIView.as_view()
