from rest_framework import serializers


class MatchedSkillSerializer(serializers.Serializer):
    skill_id = serializers.IntegerField()
    skill_name = serializers.CharField()
    is_required = serializers.BooleanField()
    candidate_level = serializers.CharField()
    required_level = serializers.CharField()
    candidate_years = serializers.IntegerField()
    required_years = serializers.IntegerField()


class MissingSkillSerializer(serializers.Serializer):
    skill_id = serializers.IntegerField()
    skill_name = serializers.CharField()
    is_required = serializers.BooleanField()
    required_level = serializers.CharField()
    required_years = serializers.IntegerField()


class SkillMatchSerializer(serializers.Serializer):
    matched_skills = MatchedSkillSerializer(many=True)
    missing_skills = MissingSkillSerializer(many=True)
    match_percentage = serializers.FloatField()
    total_vacancy_skills = serializers.IntegerField()
    total_required_skills = serializers.IntegerField()
    matched_required_skills = serializers.IntegerField()
    matched_total_skills = serializers.IntegerField()
