from rest_framework import serializers

from apps.skills.models import LearningMaterial, SkillLearningMaterial


class LearningMaterialSerializer(serializers.ModelSerializer):
    title_localized = serializers.SerializerMethodField()

    class Meta:
        model = LearningMaterial
        fields = [
            "id",
            "title",
            "title_localized",
            "description",
            "material_type",
            "source",
            "url",
            "duration_hours",
            "language",
            "rating",
            "is_free",
        ]
        read_only_fields = fields

    def get_title_localized(self, obj):
        lang = self.context.get("language", "en")
        if lang == "ru":
            return obj.title_ru or obj.title
        if lang == "uz":
            return obj.title_uz or obj.title
        return obj.title


class SkillLearningMaterialSerializer(serializers.ModelSerializer):
    material = serializers.SerializerMethodField()

    class Meta:
        model = SkillLearningMaterial
        fields = [
            "id",
            "material",
            "relevance_score",
            "is_top_match",
            "relevance_reason",
            "vacancy_match_percentage",
        ]
        read_only_fields = fields

    def get_material(self, obj):
        return LearningMaterialSerializer(
            obj.material,
            context=self.context,
        ).data
