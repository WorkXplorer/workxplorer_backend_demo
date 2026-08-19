from rest_framework import generics
from rest_framework.permissions import AllowAny

from core.responses import APIResponse
from drf_spectacular.utils import extend_schema, OpenApiParameter

from django_filters import rest_framework as filters

from ..models import QuizType, Quiz, Question
from ..serializers import (
    QuizTypeSerializer,
    QuestionSerializer,
)
from django.utils.translation import gettext as _


class QuizFilter(filters.FilterSet):
    """
    Filter class for Quiz model.
    Allows filtering quizzes by quiz_type ID.
    """

    quiz_type_id = filters.NumberFilter(field_name="quiz_type__id", lookup_expr="exact")

    class Meta:
        model = Quiz
        fields = ["quiz_type_id"]


class QuizTypeListAPIView(generics.ListAPIView):
    """
    API view to retrieve a list of active quiz types.
    """

    serializer_class = QuizTypeSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    filter_backends = [filters.DjangoFilterBackend]
    filterset_fields = ["id"]

    @extend_schema(
        summary="List quiz types",
        description="Retrieve all active quiz types available in the system.",
        responses={200: QuizTypeSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return QuizType.objects.filter(is_active=True).prefetch_related("domains")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return APIResponse.success(
            data={"results": serializer.data},
            message=_("Quiz types retrieved"),
        )


class QuestionListAPIView(generics.ListAPIView):
    """
    API view to retrieve a list of questions, optionally filtered by quiz.
    LEGACY ENDPOINT - use QuizDetailAPIView for new implementations.
    """

    serializer_class = QuestionSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    @extend_schema(
        summary="List questions",
        description="Retrieve questions. Can be filtered by quiz_id.",
        parameters=[
            OpenApiParameter(
                name="quiz_id",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Filter questions by quiz ID",
                required=False,
            )
        ],
        responses={200: QuestionSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Question.objects.filter(is_active=True).prefetch_related("answers")

        quiz_id = self.request.query_params.get("quiz_id")
        if quiz_id:
            queryset = queryset.filter(quiz_id=quiz_id)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return APIResponse.success(
            data={"results": serializer.data},
            message=_("Questions retrieved"),
        )


quiz_type_list_view = QuizTypeListAPIView.as_view()
question_list_view = QuestionListAPIView.as_view()
