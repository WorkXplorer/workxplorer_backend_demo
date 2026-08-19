from collections import defaultdict

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.authentication.models import Candidate
from apps.domain.models import Domain
from core.responses import APIResponse
from utils.language import get_request_language

from ..models import Quiz, QuizResult, AnswerChoice


def _parse_integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_localized_career_content(choice, lang):
    if lang == "uz":
        title = (
            choice.get("career_option__title_uz")
            or choice.get("career_option__title_en")
            or choice.get("career_option__title")
        )
        description = (
            choice.get("career_option__description_uz")
            or choice.get("career_option__description_en")
            or choice.get("career_option__description")
        )
    elif lang == "ru":
        title = (
            choice.get("career_option__title_ru")
            or choice.get("career_option__title_en")
            or choice.get("career_option__title")
        )
        description = (
            choice.get("career_option__description_ru")
            or choice.get("career_option__description_en")
            or choice.get("career_option__description")
        )
    else:
        title = choice.get("career_option__title_en") or choice.get("career_option__title")
        description = choice.get("career_option__description_en") or choice.get(
            "career_option__description"
        )

    return title, description or ""


class CalculateQuizResultAPIView(APIView):
    """
    API endpoint to calculate quiz results from {question_id, answer} pairs.

    - Authenticated candidates receive inline quiz results.
    - Anonymous users must supply an ``email`` field and receive a message
      telling them the results were sent by email.  Three outcomes:

        ``create_profile`` - brand-new email (candidate auto-created, result email sent).
        ``register``       - email exists but no CandidateProfile yet (set-password email).
        ``login``          - email exists with a full CandidateProfile (inline results +
                             login-CTA email).
    """

    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Calculate quiz results",
        description=(
            "Calculates quiz results from the provided responses. "
            "Authenticated candidates receive inline results. "
            "Anonymous users must supply their ``email`` and receive an email with results. "
            "Response includes a ``status`` field: "
            "``create_profile`` / ``register`` / ``login`` for anonymous users."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "quiz_id": {"type": "integer", "example": 1},
                    "email": {
                        "type": "string",
                        "example": "user@example.com",
                        "description": "Required for anonymous users only.",
                    },
                    "domain_id": {
                        "type": "integer",
                        "example": 2,
                        "description": "Optional. Auto-detected from quiz type if omitted.",
                    },
                    "responses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question_id": {"type": "integer"},
                                "answer": {"type": "array", "items": {"type": "integer"}},
                            },
                            "required": ["question_id", "answer"],
                        },
                    },
                },
                "required": ["quiz_id", "responses"],
            }
        },
        responses={
            200: OpenApiResponse(description="Results returned (authenticated) or email sent (anonymous)"),
            400: OpenApiResponse(description="Bad request"),
            404: OpenApiResponse(description="Quiz not found"),
        },
    )
    def post(self, request, *args, **kwargs):
        """
        Calculate quiz results.

        Authenticated candidates receive inline results.
        Anonymous users receive an email with the results and a status field.
        """
        quiz_id = _parse_integer(request.data.get("quiz_id"))
        if quiz_id is None:
            return APIResponse.bad_request(message=_("quiz_id is required"))

        try:
            quiz = Quiz.objects.select_related("quiz_type").get(id=quiz_id, is_active=True)
        except Quiz.DoesNotExist:
            return APIResponse.not_found(message=_("Quiz not found"))

        responses = request.data.get("responses", [])
        if not responses:
            return APIResponse.bad_request(message=_("Responses are required"))

        if not isinstance(responses, list):
            return APIResponse.bad_request(message=_("Responses are required"))

        answer_ids = set()
        question_answer_pairs = []
        seen_pairs = set()
        for response_index, resp in enumerate(responses):
            if not isinstance(resp, dict):
                return APIResponse.bad_request(
                    message=_("Responses are required"),
                    details=_("Each response must be an object."),
                )

            question_id = _parse_integer(resp.get("question_id"))
            if question_id is None:
                return APIResponse.bad_request(
                    message=_("No valid answers provided"),
                    details=_("question_id must be a valid integer at index %(index)s.")
                    % {"index": response_index},
                )

            resp_answer_ids = resp.get("answer", [])
            if not isinstance(resp_answer_ids, list) or not resp_answer_ids:
                return APIResponse.bad_request(
                    message=_("No valid answers provided"),
                    details=_("answer must be a non-empty list at index %(index)s.")
                    % {"index": response_index},
                )

            for answer_id in resp_answer_ids:
                parsed_answer_id = _parse_integer(answer_id)
                if parsed_answer_id is None:
                    return APIResponse.bad_request(
                        message=_("No valid answers provided"),
                        details=_("Answer IDs must be valid integers."),
                    )

                pair = (question_id, parsed_answer_id)
                if pair in seen_pairs:
                    continue

                seen_pairs.add(pair)
                answer_ids.add(parsed_answer_id)
                question_answer_pairs.append(pair)

        if not answer_ids:
            return APIResponse.bad_request(message=_("No valid answers provided"))

        lang = get_request_language()

        answer_choices = (
            AnswerChoice.objects.select_related("career_option")
            .filter(id__in=answer_ids, question__quiz=quiz)
            .values(
                "id",
                "question_id",
                "point",
                "career_option__id",
                "career_option__title_en",
                "career_option__title_uz",
                "career_option__title_ru",
                "career_option__title",
                "career_option__description_en",
                "career_option__description_uz",
                "career_option__description_ru",
                "career_option__description",
            )
        )

        if not answer_choices:
            return APIResponse.bad_request(
                message=_("No valid answers provided for this quiz")
            )

        answer_lookup = {}
        career_details = {}
        score_map = defaultdict(int)

        for choice in answer_choices:
            career_title, position_description = _get_localized_career_content(choice, lang)
            key = (choice["question_id"], choice["id"])
            answer_lookup[key] = {
                "point": choice["point"],
                "career_option_id": choice.get("career_option__id"),
                "career_title": career_title,
                "position_description": position_description,
            }
            career_option_id = choice.get("career_option__id")
            if career_option_id and career_option_id not in career_details:
                career_details[career_option_id] = {
                    "id": career_option_id,
                    "position": career_title,
                    "position_description": position_description,
                }

        invalid_pairs = [
            {"question_id": question_id, "answer_id": answer_id}
            for question_id, answer_id in question_answer_pairs
            if (question_id, answer_id) not in answer_lookup
        ]
        if invalid_pairs:
            return APIResponse.bad_request(
                message=_("No valid answers provided for this quiz"),
                details={"invalid_responses": invalid_pairs},
            )

        for question_id, answer_id in question_answer_pairs:
            answer_data = answer_lookup.get((question_id, answer_id))
            if (
                answer_data
                and answer_data["career_option_id"]
                and answer_data["career_title"]
            ):
                score_map[answer_data["career_option_id"]] += answer_data["point"]

        results = []
        for career_option_id, score in score_map.items():
            career_data = career_details.get(career_option_id)
            if not career_data:
                continue
            results.append(
                {
                    "id": career_data["id"],
                    "position": career_data["position"],
                    "score": score,
                    "percentage": "",
                    "position_description": career_data["position_description"],
                }
            )

        if not results:
            return APIResponse.bad_request(message=_("No valid answers provided"))

        results = sorted(results, key=lambda x: x["score"], reverse=True)

        SCORE_BASE = 75
        SCORE_RANGE = 20
        MIN_RATIO = 0.4
        MIN_RESULTS = 2

        max_score = results[0]["score"] if results else 0
        score_denominator = max(max_score, 1)
        filtered = [r for r in results if r["score"] >= max_score * MIN_RATIO]
        if len(filtered) < min(MIN_RESULTS, len(results)):
            filtered = results[:MIN_RESULTS]
        for r in filtered:
            normalized = SCORE_BASE + round(
                (r["score"] / score_denominator) * SCORE_RANGE
            )
            r["percentage"] = f"{normalized}%"
        results = filtered

        # Resolve domain
        domain_id = request.data.get("domain_id")
        domain = None
        if domain_id not in (None, ""):
            domain_id = _parse_integer(domain_id)
            if domain_id is None:
                return APIResponse.bad_request(
                    message=_("domain_id must be a valid integer")
                )
            domain = Domain.objects.filter(id=domain_id).first()
            if domain is None:
                return APIResponse.bad_request(message=_("Invalid domain_id"))
        else:
            domain = quiz.quiz_type.domains.order_by("id").first()

        # Structured top-3 for persistence - store only position_id so translations
        # are resolved at read time from CareerOption in the request language.
        top_careers_structured = [
            {
                "id": r["id"],
                "score": r["score"],
                "percentage": r["percentage"],
            }
            for r in results[:3]
        ]

        # Email needs the full localized data.
        career_options_for_email = [
            {
                "id": r["id"],
                "position": r["position"],
                "score": r["score"],
                "percentage": r["percentage"],
                "position_description": r["position_description"],
            }
            for r in results[:3]
        ]

        # ── Authenticated flow ──────────────────────────────────────────────
        if request.user.is_authenticated:
            candidate = request.user.candidate
            QuizResult.objects.create(
                candidate=candidate,
                quiz=quiz,
                career_options=top_careers_structured,
                domain=domain,
            )
            return APIResponse.success(
                data={"results": results},
                message=_("Quiz results calculated successfully"),
            )

        # ── Anonymous flow ──────────────────────────────────────────────────
        email_raw = request.data.get("email", "")
        if not email_raw or not str(email_raw).strip():
            return APIResponse.bad_request(
                message=_("email is required for anonymous users")
            )

        email = str(email_raw).strip().lower()
        try:
            validate_email(email)
        except DjangoValidationError:
            return APIResponse.bad_request(message=_("Enter a valid email address."))

        from apps.profiles.models import CandidateProfile
        from apps.quiz.services.pending_quiz_service import store_pending
        from apps.quiz.services.email_service import send_quiz_result_email

        existing_candidate = Candidate.objects.filter(email=email).first()

        if existing_candidate is None:
            # Case 1 - brand-new email
            new_candidate = Candidate.objects.create_user(
                email=email,
                password=None,
                is_candidate=True,
                is_active=True,
                preferred_language=lang,
            )
            QuizResult.objects.create(
                candidate=new_candidate,
                quiz=quiz,
                career_options=top_careers_structured,
                domain=domain,
            )
            send_quiz_result_email(new_candidate, career_options_for_email, lang)
            return APIResponse.success(
                data={"status": "create_profile"},
                message=_("Your quiz results have been sent to your email."),
            )

        has_profile = CandidateProfile.objects.filter(
            candidate=existing_candidate
        ).exists()

        if not has_profile:
            # Case 2 - email exists, no CandidateProfile
            result = QuizResult.objects.create(
                candidate=None,
                quiz=quiz,
                career_options=top_careers_structured,
                domain=domain,
            )
            store_pending(email, str(result.id))
            _send_set_password_email(existing_candidate, lang)
            return APIResponse.success(
                data={"status": "register"},
                message=_("Your quiz results have been sent to your email."),
            )

        # Case 3 - email exists with full CandidateProfile
        result = QuizResult.objects.create(
            candidate=None,
            quiz=quiz,
            career_options=top_careers_structured,
            domain=domain,
        )
        store_pending(email, str(result.id))
        return APIResponse.success(
            data={"results": results, "status": "login"},
            message=_("Quiz completed successfully. Log in to see your quiz result."),
        )


def _send_set_password_email(candidate, language: str) -> None:
    """Send the set-password email in the anonymous quiz case-2 path."""
    import logging
    from django.conf import settings
    from django.contrib.auth.tokens import default_token_generator as _token_gen
    from utils import encode_uid
    from apps.general.services.email_service import send_email_from_template_type

    _logger = logging.getLogger(__name__)
    try:
        uid = encode_uid(candidate.pk)
        token = _token_gen.make_token(candidate)
        set_password_url = (
            f"{settings.FRONTEND_URL}/set-password/candidate/{uid}/{token}/"
        )
        context = {
            "user_email": candidate.email,
            "set_password_url": set_password_url,
            "site_name": getattr(settings, "SITE_NAME", "WorkXplorer"),
        }
        send_email_from_template_type(
            to_email=candidate.email,
            template_type="set-password",
            context=context,
            language=language,
            delay_seconds=0,
        )
        _logger.info("Set-password email queued for candidate %s (quiz flow)", candidate.id)
    except Exception:
        _logger.exception(
            "Failed to queue set-password email for candidate %s (quiz flow)", candidate.id
        )


calculate_quiz_result_view = CalculateQuizResultAPIView.as_view()
