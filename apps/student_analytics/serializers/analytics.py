from rest_framework import serializers

from apps.student_analytics.models import StudentAnalytics, SkillRoadmap, RoadmapItem


class RoadmapItemSerializer(serializers.ModelSerializer):
    skill_id = serializers.IntegerField(source="skill.id", read_only=True, default=None)
    skill_name_localized = serializers.SerializerMethodField()

    class Meta:
        model = RoadmapItem
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
            "vacancy_count",
            "salary_impact_percentage",
            "learning_time_hours",
            "learning_time_weeks",
            "context_message",
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


class SkillRoadmapSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    def get_items(self, obj):
        return RoadmapItemSerializer(
            obj.items.all(),
            many=True,
            context=self.context,
        ).data

    class Meta:
        model = SkillRoadmap
        fields = [
            "id",
            "target_role",
            "ai_model",
            "generated_at",
            "items",
        ]
        read_only_fields = fields


class StudentAnalyticsSerializer(serializers.ModelSerializer):
    roadmap = serializers.SerializerMethodField()

    def get_roadmap(self, obj):
        try:
            roadmap = obj.roadmap
        except Exception:
            return None
        if not roadmap:
            return None
        return SkillRoadmapSerializer(roadmap, context=self.context).data

    class Meta:
        model = StudentAnalytics
        fields = [
            "id",
            "target_role",
            "market_match_percentage",
            "market_match_insight",
            "track_progress_percentage",
            "verified_skills_count",
            "total_roadmap_skills",
            "strong_skills",
            "skills_to_improve",
            "last_computed_at",
            "roadmap",
        ]
        read_only_fields = fields


class UpdateTargetRoleSerializer(serializers.Serializer):
    target_role = serializers.CharField(max_length=255)
    resume_id = serializers.UUIDField(required=False)
