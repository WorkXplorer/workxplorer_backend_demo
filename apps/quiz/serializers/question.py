from rest_framework import serializers

from apps.quiz.models import AnswerChoice, Question, QuizType
from apps.domain.serializers import DomainListSerializer


class AnswerChoiceSerializer(serializers.ModelSerializer):
    """
    Serializer for answer data.
    It includes the answer ID and text.
    This serializer is used to represent an answer in a simplified format,
    typically for listing answers associated with a question.
    """

    class Meta:
        model = AnswerChoice
        fields = ("id", "text")


class AnswerChoiceWithDomainSerializer(serializers.ModelSerializer):
    """
    Serializer for answer data with domain information.
    Used for domain-discovery questions where domain mapping is important.
    """

    domains = DomainListSerializer(many=True, read_only=True)

    class Meta:
        model = AnswerChoice
        fields = ("id", "text", "point", "domains")


class QuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for question data.
    It includes only the question ID and title.
    This serializer is used to represent a question in a simplified format,
    typically for listing questions without their answers.
    """

    answers = AnswerChoiceSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ("id", "title", "answers")


class QuizTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for quiz types with domain information.
    """

    domains = DomainListSerializer(many=True, read_only=True)

    class Meta:
        model = QuizType
        fields = ["id", "name", "description", "domains", "is_active", "created_at"]
