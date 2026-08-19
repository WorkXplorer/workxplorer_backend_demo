from collections import defaultdict

from django.db.models import Prefetch

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from core.responses import APIResponse
from utils.language import get_request_language

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

from ..models import Quiz, Question, AnswerChoice
from ..serializers import QuestionSerializer
from django.utils.translation import gettext as _


def _parse_integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_localized_domain_content(answer, lang):
    if lang == "uz":
        name = (
            answer.get("domains__name_uz")
            or answer.get("domains__name_en")
            or answer.get("domains__name")
        )
        description = (
            answer.get("domains__description_uz")
            or answer.get("domains__description_en")
            or answer.get("domains__description")
        )
    elif lang == "ru":
        name = (
            answer.get("domains__name_ru")
            or answer.get("domains__name_en")
            or answer.get("domains__name")
        )
        description = (
            answer.get("domains__description_ru")
            or answer.get("domains__description_en")
            or answer.get("domains__description")
        )
    else:
        name = answer.get("domains__name_en") or answer.get("domains__name")
        description = answer.get("domains__description_en") or answer.get(
            "domains__description"
        )

    return name, description or ""


class DetermineDomainAPIView(APIView):
    """
    API endpoint to determine candidate's preferred domain based on their answers.
    
    Flow:
    1. Receive answers from domain-discovery questions (first 5-10 questions)
    2. Calculate which domain has the highest score based on answers
    3. Find quiz types associated with that domain
    4. Return questions from those quiz types for the second phase
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Determine domain and get domain-specific questions",
        description=(
                "This endpoint analyzes the candidate's answers to domain-discovery questions "
                "and determines their preferred domain/field. It then returns questions "
                "from quiz types associated with that domain for the second phase of the quiz.\n\n"
                "**Flow:**\n"
                "1. Submit answers to domain-discovery questions (quiz_id=1)\n"
                "2. System calculates domain scores based on answer->domain mappings\n"
                "3. Returns questions from quiz types linked to the determined domain"
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "quiz_id": {
                        "type": "integer",
                        "example": 1,
                        "description": "ID of the domain-discovery quiz",
                    },
                    "responses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_id": {"type": "integer", "example": 1},
                                "answer_id": {"type": "integer", "example": 10},
                            },
                            "required": ["question_id", "answer_id"],
                        },
                        "description": "List of question and answer ID pairs",
                    },
                },
                "required": ["quiz_id", "responses"],
            }
        },
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "determined_domain": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer", "example": 1},
                                "name": {"type": "string", "example": "IT"},
                                "description": {
                                    "type": "string",
                                    "example": "Information Technology",
                                },
                                "score": {"type": "integer", "example": 25},
                                "percentage": {"type": "string", "example": "60%"},
                            },
                        },
                        "all_domain_scores": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "domain_id": {"type": "integer"},
                                    "domain_name": {"type": "string"},
                                    "score": {"type": "integer"},
                                    "percentage": {"type": "string"},
                                },
                            },
                        },
                        "quiz_id": {
                            "oneOf": [
                                {"type": "integer", "example": 3},
                                {"type": "array", "items": {"type": "integer"}, "example": [3, 4, 5]}
                            ],
                            "description": "Quiz ID(s) that contain the returned questions. Single ID if all questions from one quiz, array if from multiple quizzes."
                        },
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer"},
                                    "title": {"type": "string"},
                                    "answers": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "text": {"type": "string"},
                                                "point": {"type": "integer"},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                description="Domain determined successfully with next questions",
            ),
            400: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "error": {"type": "string", "example": "quiz_id is required"}
                    },
                },
                description="Bad request - missing required fields or invalid data",
            ),
            404: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "error": {"type": "string", "example": "Quiz not found"}
                    },
                },
                description="Quiz or domain not found",
            ),
        },
        examples=[
            OpenApiExample(
                "Valid request example",
                value={
                    "quiz_id": 1,
                    "responses": [
                        {"question_id": 1, "answer_id": 10},
                        {"question_id": 2, "answer_id": 15},
                        {"question_id": 3, "answer_id": 22},
                    ],
                },
                request_only=True,
            ),
            OpenApiExample(
                "Successful response example",
                value={
                    "determined_domain": {
                        "id": 1,
                        "name": "IT",
                        "description": "Information Technology",
                        "score": 25,
                        "percentage": "60%",
                    },
                    "all_domain_scores": [
                        {
                            "domain_id": 1,
                            "domain_name": "IT",
                            "score": 25,
                            "percentage": "60%",
                        },
                        {
                            "domain_id": 2,
                            "domain_name": "Healthcare",
                            "score": 10,
                            "percentage": "24%",
                        },
                    ],
                    "quiz_id": 3,
                    "questions": [
                        {
                            "id": 11,
                            "title": "What programming language interests you?",
                            "answers": [
                                {"id": 101, "text": "Python", "point": 10},
                                {"id": 102, "text": "JavaScript", "point": 10},
                            ],
                        }
                    ],
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        """
        Determine domain based on answers and return domain-specific questions.
        """
        # Validate request
        quiz_id = _parse_integer(request.data.get("quiz_id"))
        if quiz_id is None:
            return APIResponse.bad_request(message=_("quiz_id is required"))

        responses = request.data.get("responses", [])
        if not responses:
            return APIResponse.bad_request(message=_("Responses are required"))
        if not isinstance(responses, list):
            return APIResponse.bad_request(message=_("Responses are required"))

        # Verify quiz exists and is active
        try:
            quiz = Quiz.objects.select_related("quiz_type").get(
                id=quiz_id, is_active=True
            )
        except Quiz.DoesNotExist:
            return APIResponse.not_found(message=_("Quiz not found"))

        # Extract answer IDs from responses
        answer_ids = set()
        question_answer_pairs = []
        seen_pairs = set()
        for response_index, resp in enumerate(responses):
            if not isinstance(resp, dict):
                return APIResponse.bad_request(
                    message=_("No valid answers provided"),
                    details=_("Each response must be an object."),
                )

            question_id = _parse_integer(resp.get("question_id"))
            answer_id = _parse_integer(resp.get("answer_id"))
            if question_id is None or answer_id is None:
                return APIResponse.bad_request(
                    message=_("No valid answers provided"),
                    details=_(
                        "question_id and answer_id must be valid integers at index %(index)s."
                    )
                    % {"index": response_index},
                )

            pair = (question_id, answer_id)
            if pair in seen_pairs:
                continue

            seen_pairs.add(pair)
            answer_ids.add(answer_id)
            question_answer_pairs.append(pair)

        if not answer_ids:
            return APIResponse.bad_request(message=_("No valid answers provided"))

        # Get current language for localized responses
        lang = get_request_language()

        # Query answer choices with domain info through M2M relationship
        # Each answer can map to multiple domains; each (answer, domain) pair
        # contributes the answer's points to that domain's score.
        answer_domain_data = (
            AnswerChoice.objects.filter(
                id__in=answer_ids,
                question__quiz=quiz,
                domains__isnull=False,  # Only answers with domain mapping
            )
            .values(
                "id",
                "question_id",
                "point",
                "domains__id",
                "domains__name",
                "domains__name_en",
                "domains__name_uz",
                "domains__name_ru",
                "domains__description",
                "domains__description_en",
                "domains__description_uz",
                "domains__description_ru",
            )
            .distinct()
        )

        if not answer_domain_data:
            return APIResponse.bad_request(
                message=_("No valid answers with domain mapping found for this quiz")
            )

        valid_pairs = {
            (answer["question_id"], answer["id"])
            for answer in answer_domain_data
        }
        invalid_pairs = [
            {"question_id": question_id, "answer_id": answer_id}
            for question_id, answer_id in question_answer_pairs
            if (question_id, answer_id) not in valid_pairs
        ]
        if invalid_pairs:
            return APIResponse.bad_request(
                message=_("No valid answers with domain mapping found for this quiz"),
                details={"invalid_responses": invalid_pairs},
            )

        # Calculate domain scores
        domain_scores = defaultdict(int)
        domain_info = {}

        for answer in answer_domain_data:
            domain_id = answer["domains__id"]
            point = answer["point"]
            domain_scores[domain_id] += point

            # Store domain info with localized name
            if domain_id not in domain_info:
                name, description = _get_localized_domain_content(answer, lang)

                domain_info[domain_id] = {
                    "id": domain_id,
                    "name": name,
                    "description": description or "",
                }

        if not domain_scores:
            return APIResponse.bad_request(
                message=_("Could not determine domain from provided answers")
            )

        # Calculate percentages and find winning domain
        total_score = sum(domain_scores.values()) or 1
        all_domain_scores = []

        for domain_id, score in sorted(
            domain_scores.items(), key=lambda x: x[1], reverse=True
        ):
            percentage = f"{round((score / total_score) * 100)}%"
            all_domain_scores.append(
                {
                    "domain_id": domain_id,
                    "domain_name": domain_info[domain_id]["name"],
                    "score": score,
                    "percentage": percentage,
                }
            )

        # Determine the winning domain (highest score)
        winning_domain_id = max(domain_scores.items(), key=lambda x: x[1])[0]
        winning_domain = domain_info[winning_domain_id]
        winning_domain["score"] = domain_scores[winning_domain_id]
        winning_domain["percentage"] = (
            f"{round((winning_domain['score'] / total_score) * 100)}%"
        )

        # Build ranked list of domain IDs by score (highest first)
        ranked_domain_ids = [
            d["domain_id"] for d in all_domain_scores
        ]

        # Pre-compute which ranked domains actually have active questions.
        # Single query replaces a loop that ran .exists() per domain.
        active_domain_ids = set(
            Question.objects.filter(
                is_active=True,
                quiz__is_active=True,
                quiz__quiz_type__is_active=True,
                quiz__quiz_type__domains__in=ranked_domain_ids,
            )
            .values_list("quiz__quiz_type__domains", flat=True)
        )

        selected_domain_id = next(
            (d_id for d_id in ranked_domain_ids if d_id in active_domain_ids),
            None,
        )

        if selected_domain_id is not None:
            domain_questions = (
                Question.objects.filter(
                    is_active=True,
                    quiz__is_active=True,
                    quiz__quiz_type__domains=selected_domain_id,
                    quiz__quiz_type__is_active=True,
                )
                .select_related("quiz", "quiz__quiz_type")
                .prefetch_related(
                    "quiz__quiz_type__domains",
                    Prefetch(
                        "answers",
                        queryset=AnswerChoice.objects.only(
                            "id", "text", "question_id"
                        ),
                    ),
                )
                .only("id", "title", "quiz_id")
                .distinct()
            )
        else:
            domain_questions = Question.objects.none()

        # Serialize questions
        questions_serializer = QuestionSerializer(domain_questions, many=True)

        # Collect unique quiz IDs from the returned questions
        quiz_ids = sorted({question.quiz.id for question in domain_questions})
        # If there's only one unique quiz_id, return it as a single integer
        # Otherwise, return the list of quiz_ids
        quiz_id_response = quiz_ids[0] if len(quiz_ids) == 1 else quiz_ids

        return APIResponse.success(
            data={
                "determined_domain": winning_domain,
                "all_domain_scores": all_domain_scores,
                "quiz_id": quiz_id_response,
                "questions": questions_serializer.data,
            },
            message=_("Domain determined successfully"),
        )


determine_domain_view = DetermineDomainAPIView.as_view()
