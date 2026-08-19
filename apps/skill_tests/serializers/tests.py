from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.skill_tests.models import SkillTest, TestQuestion, TestAttempt, TestAnswer


class TestQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestQuestion
        fields = [
            "id",
            "order",
            "question_type",
            "question_text",
            "options",
            "points",
            "category",
        ]
        read_only_fields = fields


class SkillTestSerializer(serializers.ModelSerializer):
    skill_name = serializers.CharField(source="skill.name", read_only=True)
    skill_id = serializers.IntegerField(source="skill.id", read_only=True)

    class Meta:
        model = SkillTest
        fields = [
            "id",
            "skill_id",
            "skill_name",
            "target_level",
            "title",
            "time_limit_minutes",
            "total_questions",
            "passing_score",
            "ai_model",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TestAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestAnswer
        fields = [
            "id",
            "question",
            "selected_option_id",
            "open_ended_text",
            "is_correct",
            "points_earned",
            "ai_evaluation",
            "answered_at",
        ]
        read_only_fields = [
            "id", "question", "is_correct", "points_earned", "ai_evaluation", "answered_at"
        ]


class TestAttemptSerializer(serializers.ModelSerializer):
    test = SkillTestSerializer(read_only=True)
    answers = TestAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = TestAttempt
        fields = [
            "id",
            "test",
            "status",
            "started_at",
            "completed_at",
            "score_percentage",
            "total_points",
            "earned_points",
            "passed",
            "result_message",
            "strengths",
            "weaknesses",
            "answers",
        ]
        read_only_fields = fields


class TestAttemptSummarySerializer(serializers.ModelSerializer):
    test = SkillTestSerializer(read_only=True)

    class Meta:
        model = TestAttempt
        fields = [
            "id",
            "test",
            "status",
            "started_at",
            "completed_at",
            "score_percentage",
            "passed",
        ]
        read_only_fields = fields


class GenerateTestSerializer(serializers.Serializer):
    skill_id = serializers.IntegerField()
    target_level = serializers.CharField(max_length=20, default="INTERMEDIATE")
    ai_model = serializers.CharField(max_length=30, default="default")


class StartTestSerializer(serializers.Serializer):
    resume_id = serializers.UUIDField(required=False)
    roadmap_item_id = serializers.UUIDField(required=False)
    vacancy_roadmap_item_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if attrs.get("roadmap_item_id") and attrs.get("vacancy_roadmap_item_id"):
            raise serializers.ValidationError(
                _("Only one of roadmap_item_id or vacancy_roadmap_item_id may be provided.")
            )
        return attrs


class SubmitAnswerItemSerializer(serializers.Serializer):
    question_id = serializers.UUIDField()
    selected_option_id = serializers.CharField(max_length=10, required=False, default="")
    open_ended_text = serializers.CharField(required=False, default="")


class SubmitAttemptSerializer(serializers.Serializer):
    answers = SubmitAnswerItemSerializer(many=True, write_only=True, min_length=1)
    ai_model = serializers.CharField(max_length=30, default="default")
