import logging
from datetime import datetime, timezone as dt_timezone

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.general.services.skill_recommendation import get_candidate_resume
from apps.skills.models import Skill
from apps.skill_tests.models import SkillTest, TestAttempt
from apps.skill_tests.serializers import (
    SkillTestSerializer,
    TestQuestionSerializer,
    TestAttemptSerializer,
    TestAttemptSummarySerializer,
    GenerateTestSerializer,
    StartTestSerializer,
    SubmitAttemptSerializer,
)
from apps.skill_tests.services import generate_test, submit_attempt, validate_attempt_limits
from apps.student_analytics.models import RoadmapItem, VacancyRoadmapItem
from core.responses import APIResponse

logger = logging.getLogger(__name__)


class SkillTestThrottle(UserRateThrottle):
    scope = "skill_test"


class GenerateTestAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SkillTestThrottle]

    def post(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can generate tests."))

        serializer = GenerateTestSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(field_errors=serializer.errors)

        data = serializer.validated_data
        try:
            skill = Skill.objects.get(id=data["skill_id"], is_active=True)
        except Skill.DoesNotExist:
            return APIResponse.not_found(message=_("Skill not found."))

        ai_model = data.get("ai_model", "groq")
        if ai_model not in ("groq",):
            return APIResponse.bad_request(message=_("ai_model must be 'groq'."))

        today_start_utc = datetime.now(dt_timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        with transaction.atomic():
            user._meta.model.objects.select_for_update().get(id=user.id)

            existing_test = SkillTest.objects.filter(
                candidate=user,
                skill=skill,
                created_at__gte=today_start_utc,
            ).select_related("skill").order_by("-created_at").first()
            if existing_test:
                return APIResponse.success(
                    data=SkillTestSerializer(existing_test).data,
                    message=_("You already generated a test for this skill today."),
                )

            test = generate_test(
                skill,
                target_level=data.get("target_level", "INTERMEDIATE"),
                candidate=user,
                ai_model=ai_model,
            )

        return APIResponse.created(
            data=SkillTestSerializer(test).data,
            message=_("Test generated successfully."),
        )


class StartTestAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SkillTestThrottle]

    def get(self, request, test_id, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can start tests."))

        try:
            test = SkillTest.objects.get(id=test_id, candidate=user, is_active=True)
        except (SkillTest.DoesNotExist, ValueError):
            return APIResponse.not_found(message=_("Test not found."))

        try:
            validate_attempt_limits(user, test)
        except ValidationError as e:
            return APIResponse.bad_request(message=e.messages[0] if e.messages else str(e))
        except Exception as e:
            return APIResponse.bad_request(message=str(e))

        serializer = StartTestSerializer(data=request.query_params)
        if not serializer.is_valid():
            return APIResponse.validation_error(field_errors=serializer.errors)

        data = serializer.validated_data

        resume_id = data.get("resume_id")
        resume = get_candidate_resume(user, resume_id)
        if not resume:
            return APIResponse.not_found(message=_("Resume not found."))

        roadmap_item_id = data.get("roadmap_item_id")
        roadmap_item = None
        if roadmap_item_id:
            try:
                roadmap_item = RoadmapItem.objects.get(
                    id=roadmap_item_id,
                    roadmap__analytics__candidate=user,
                )
                if roadmap_item.status == RoadmapItem.Status.VERIFIED:
                    return APIResponse.bad_request(message=_("This skill is already verified."))
            except RoadmapItem.DoesNotExist:
                return APIResponse.not_found(message=_("Roadmap item not found."))
            except ValueError:
                return APIResponse.bad_request(message=_("Invalid roadmap_item_id."))

        vacancy_roadmap_item_id = data.get("vacancy_roadmap_item_id")
        vacancy_roadmap_item = None
        if vacancy_roadmap_item_id:
            try:
                vacancy_roadmap_item = VacancyRoadmapItem.objects.get(
                    id=vacancy_roadmap_item_id,
                    roadmap__application__candidate=user,
                )
                if vacancy_roadmap_item.status == VacancyRoadmapItem.Status.VERIFIED:
                    return APIResponse.bad_request(message=_("This skill is already verified."))
            except VacancyRoadmapItem.DoesNotExist:
                return APIResponse.not_found(message=_("Vacancy roadmap item not found."))
            except ValueError:
                return APIResponse.bad_request(message=_("Invalid vacancy_roadmap_item_id."))

        with transaction.atomic():
            attempt, created = TestAttempt.objects.get_or_create(
                test=test,
                candidate=user,
                status=TestAttempt.Status.IN_PROGRESS,
                defaults={
                    "resume": resume,
                    "roadmap_item": roadmap_item,
                    "vacancy_roadmap_item": vacancy_roadmap_item,
                },
            )

        if not created:
            questions = test.questions.all().order_by("order")
            return APIResponse.success(
                data={
                    "attempt": TestAttemptSerializer(attempt).data,
                    "questions": TestQuestionSerializer(questions, many=True).data,
                },
                message=_("Resuming existing attempt."),
            )

        questions = test.questions.all().order_by("order")
        return APIResponse.created(
            data={
                "attempt": TestAttemptSerializer(attempt).data,
                "questions": TestQuestionSerializer(questions, many=True).data,
            },
            message=_("Test attempt started."),
        )


class SubmitAttemptAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SkillTestThrottle]

    def post(self, request, attempt_id, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can submit attempts."))

        try:
            attempt = TestAttempt.objects.get(
                id=attempt_id,
                candidate=user,
            )
        except (TestAttempt.DoesNotExist, ValueError):
            return APIResponse.not_found(message=_("Attempt not found."))

        if attempt.status != TestAttempt.Status.IN_PROGRESS:
            return APIResponse.bad_request(message=_("This attempt has already been submitted."))

        with transaction.atomic():
            updated = TestAttempt.objects.filter(
                id=attempt_id,
                status=TestAttempt.Status.IN_PROGRESS,
                completed_at__isnull=True,
            ).update(completed_at=timezone.now())
            if not updated:
                return APIResponse.bad_request(message=_("This attempt has already been submitted."))
            attempt.refresh_from_db()

        serializer = SubmitAttemptSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(field_errors=serializer.errors)

        answers_data = serializer.validated_data.get("answers", [])
        ai_model = serializer.validated_data.get("ai_model", "groq")

        try:
            attempt = submit_attempt(attempt, answers_data, ai_model=ai_model)
        except Exception:
            logger.exception("Failed to submit attempt %s", attempt.id)
            return APIResponse.server_error(message=_("Failed to evaluate test."))

        return APIResponse.success(
            data=TestAttemptSerializer(attempt).data,
            message=_("Test submitted successfully."),
        )


class AttemptResultAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can view results."))

        try:
            attempt = TestAttempt.objects.select_related("test__skill").prefetch_related(
                "answers__question"
            ).get(id=attempt_id, candidate=user)
        except (TestAttempt.DoesNotExist, ValueError):
            return APIResponse.not_found(message=_("Attempt not found."))

        serializer = TestAttemptSerializer(attempt)
        return APIResponse.success(data=serializer.data)


class CandidateAttemptsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        if not getattr(user, "is_candidate", False):
            return APIResponse.forbidden(message=_("Only candidates can view attempts."))

        attempts = TestAttempt.objects.filter(
            candidate=user,
            status=TestAttempt.Status.COMPLETED,
        ).select_related("test__skill").order_by("-completed_at")[:20]

        serializer = TestAttemptSummarySerializer(attempts, many=True)
        return APIResponse.success(data=serializer.data)
