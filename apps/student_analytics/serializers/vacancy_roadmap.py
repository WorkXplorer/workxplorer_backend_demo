from rest_framework import serializers

from apps.student_analytics.models import VacancySkillRoadmap, VacancyRoadmapItem


class VacancyRoadmapItemSerializer(serializers.ModelSerializer):
    skill_id = serializers.IntegerField(read_only=True)
    skill_name_localized = serializers.SerializerMethodField()

    class Meta:
        model = VacancyRoadmapItem
        fields = [
            "id",
            "skill_id",
            "skill_name",
            "skill_name_localized",
            "order",
            "target_level",
            "current_level",
            "status",
            "is_critical",
            "impact_percentage",
            "context_message",
            "learning_time_hours",
            "learning_time_weeks",
        ]
        read_only_fields = fields

    def get_skill_name_localized(self, obj):
        lang = self.context.get("language", "en")
        skill = obj.skill
        if skill:
            if lang == "ru":
                return skill.name_ru or skill.name_en or obj.skill_name
            if lang == "uz":
                return skill.name_uz or skill.name_en or obj.skill_name
            return skill.name_en or obj.skill_name
        return obj.skill_name


class VacancySkillRoadmapSerializer(serializers.ModelSerializer):
    vacancy_id = serializers.UUIDField(
        source="application.vacancy_id", read_only=True
    )
    vacancy_title = serializers.CharField(
        source="application.vacancy.title", read_only=True
    )
    company_name = serializers.CharField(
        source="application.vacancy.company.name", read_only=True
    )
    items = serializers.SerializerMethodField()

    class Meta:
        model = VacancySkillRoadmap
        fields = [
            "id",
            "vacancy_id",
            "vacancy_title",
            "company_name",
            "ai_model",
            "generated_at",
            "items",
        ]
        read_only_fields = fields

    def get_items(self, obj):
        return VacancyRoadmapItemSerializer(
            obj.items.all(),
            many=True,
            context=self.context,
        ).data
