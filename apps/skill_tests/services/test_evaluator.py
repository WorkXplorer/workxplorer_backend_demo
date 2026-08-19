import logging
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.ai.services import GroqClient
from apps.ai.services.ai_utils import parse_json_response
from apps.resumes.models import ResumeSkill
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES, user_preferred_language
from apps.student_analytics.models import RoadmapItem, VacancyRoadmapItem
from apps.student_analytics.services import analyze_strengths_weaknesses, generate_result_message
from utils.prompt_sanitizer import sanitize_prompt_list, sanitize_prompt_value

from apps.skill_tests.models import TestAttempt, TestQuestion

logger = logging.getLogger(__name__)

PASSING_THRESHOLD = Decimal("70.0")
MAX_ATTEMPTS = 3
ATTEMPT_COOLDOWN_HOURS = 24


def validate_attempt_limits(candidate, test):
    recent_cutoff = timezone.now() - timedelta(hours=ATTEMPT_COOLDOWN_HOURS)

    recent_attempts = TestAttempt.objects.filter(
        candidate=candidate,
        test=test,
        started_at__gte=recent_cutoff,
        status__in=[TestAttempt.Status.COMPLETED, TestAttempt.Status.EXPIRED],
    ).count()

    if recent_attempts >= MAX_ATTEMPTS:
        raise ValidationError(
            _("You have reached the maximum of %(max)d attempts "
              "in %(hours)d hours. Please try again later.")
            % {"max": MAX_ATTEMPTS, "hours": ATTEMPT_COOLDOWN_HOURS}
        )


def get_skill_attempt_status(candidate, skill) -> dict:
    """Today's attempt usage for a skill, without requiring a test to already
    exist — lets callers show "N of MAX_ATTEMPTS attempts left" up front."""
    from apps.skill_tests.models import SkillTest

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    test = SkillTest.objects.filter(
        candidate=candidate,
        skill=skill,
        created_at__gte=today_start,
    ).order_by("-created_at").first()

    attempts_used = 0
    if test:
        recent_cutoff = timezone.now() - timedelta(hours=ATTEMPT_COOLDOWN_HOURS)
        attempts_used = TestAttempt.objects.filter(
            candidate=candidate,
            test=test,
            started_at__gte=recent_cutoff,
            status__in=[TestAttempt.Status.COMPLETED, TestAttempt.Status.EXPIRED],
        ).count()

    return {
        "attempts_used": attempts_used,
        "attempts_remaining": max(0, MAX_ATTEMPTS - attempts_used),
        "max_attempts": MAX_ATTEMPTS,
        "cooldown_hours": ATTEMPT_COOLDOWN_HOURS,
    }


def _evaluate_open_ended(ai_client, question, candidate_answer, language):
    correct = question.correct_answer or {}
    keywords = correct.get("keywords", [])
    rubric = correct.get("rubric", "")
    sample_answer = correct.get("sample_answer", "")

    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")

    question_text = sanitize_prompt_value(question.question_text, max_length=1000)
    rubric = sanitize_prompt_value(rubric, max_length=2000)
    sample_answer = sanitize_prompt_value(sample_answer, max_length=2000)
    candidate_answer = sanitize_prompt_value(candidate_answer, max_length=5000)
    keywords = sanitize_prompt_list(keywords, max_length=100)

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a skill assessment evaluator. Respond in {lang_name}. "
                "Evaluate an open-ended answer against the rubric. Return JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question_text}\n"
                f"Rubric: {rubric}\n"
                f"Expected keywords: {keywords}\n"
                f"Sample answer: {sample_answer}\n"
                f"Candidate's answer: {candidate_answer}\n\n"
                "Score 0.0 to 1.0 based on:\n"
                "- Keyword coverage (40%)\n"
                "- Conceptual accuracy (40%)\n"
                "- Clarity and specificity (20%)\n\n"
                "Respond with JSON:\n"
                '{"score": 0.75, "feedback": "...", '
                '"matched_keywords": ["kw1"], "missing_keywords": ["kw2"]}'
            ),
        },
    ]

    response = ai_client.chat_completion(messages, temperature=0, json_mode=True)
    content = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})
    return parse_json_response(content), usage


def _score_mc(question, selected_option_id):
    correct = question.correct_answer or {}
    correct_id = correct.get("option_id", "")
    is_correct = selected_option_id.upper() == correct_id.upper() if correct_id else False
    return is_correct, Decimal(str(question.points if is_correct else 0))


def submit_attempt(attempt, answers_data, ai_model="groq"):
    time_limit = attempt.test.time_limit_minutes
    elapsed = timezone.now() - attempt.started_at
    if elapsed > timedelta(minutes=time_limit):
        attempt.status = TestAttempt.Status.EXPIRED
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["status", "completed_at", "updated_at"])
        return attempt

    language = user_preferred_language(attempt.candidate)
    ai_client = GroqClient()

    total_input_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0

    questions_by_id = {
        str(q.id): q
        for q in TestQuestion.objects.filter(test=attempt.test)
    }

    total_points = 0
    earned_points = Decimal("0")
    category_scores = {}

    answers_to_create = []

    for answer_item in answers_data:
        question_id = str(answer_item.get("question_id", ""))
        question = questions_by_id.get(question_id)
        if not question:
            continue

        selected_option_id = answer_item.get("selected_option_id", "")
        open_ended_text = answer_item.get("open_ended_text", "")
        total_points += question.points

        if question.question_type == TestQuestion.QuestionType.MULTIPLE_CHOICE:
            is_correct, pts = _score_mc(question, selected_option_id)
            answers_to_create.append({
                "question": question,
                "selected_option_id": selected_option_id,
                "open_ended_text": "",
                "is_correct": is_correct,
                "points_earned": pts,
                "ai_evaluation": {},
            })
            earned_points += pts
            cat = question.category or "general"
            if cat not in category_scores:
                category_scores[cat] = {"earned": 0, "total": 0}
            category_scores[cat]["earned"] += float(pts)
            category_scores[cat]["total"] += question.points
        elif question.question_type == TestQuestion.QuestionType.OPEN_ENDED:
            eval_result = {}
            pts = Decimal("0")
            is_correct = False
            try:
                eval_result, eval_usage = _evaluate_open_ended(
                    ai_client, question, open_ended_text, language
                )
                total_input_tokens += eval_usage.get("prompt_tokens", 0)
                total_output_tokens += eval_usage.get("completion_tokens", 0)
                total_thinking_tokens += eval_usage.get("thinking_tokens", 0)
                score = Decimal(str(eval_result.get("score", 0)))
                pts = Decimal(str(question.points)) * score
                is_correct = score >= Decimal("0.6")
            except Exception:
                logger.exception("Failed to evaluate open-ended question %s", question.id)

            answers_to_create.append({
                "question": question,
                "selected_option_id": "",
                "open_ended_text": open_ended_text,
                "is_correct": is_correct,
                "points_earned": pts,
                "ai_evaluation": eval_result,
            })
            earned_points += pts
            cat = question.category or "general"
            if cat not in category_scores:
                category_scores[cat] = {"earned": 0, "total": 0}
            category_scores[cat]["earned"] += float(pts)
            category_scores[cat]["total"] += question.points

    score_pct = round(earned_points / Decimal(str(total_points)) * 100, 1) if total_points else Decimal("0")
    passed = score_pct >= PASSING_THRESHOLD

    strengths = []
    weaknesses = []
    try:
        analysis, analysis_usage = analyze_strengths_weaknesses(
            ai_client, attempt.test.skill.name, category_scores, language
        )
        total_input_tokens += analysis_usage.get("prompt_tokens", 0)
        total_output_tokens += analysis_usage.get("completion_tokens", 0)
        total_thinking_tokens += analysis_usage.get("thinking_tokens", 0)
        strengths = analysis.get("strengths", [])
        weaknesses = analysis.get("weaknesses", [])
    except Exception:
        logger.exception("Failed to analyze strengths/weaknesses")

    result_msg = ""
    try:
        result_msg, msg_usage = generate_result_message(
            ai_client, float(score_pct), passed, attempt.test.skill.name, language
        )
        total_input_tokens += msg_usage.get("prompt_tokens", 0)
        total_output_tokens += msg_usage.get("completion_tokens", 0)
        total_thinking_tokens += msg_usage.get("thinking_tokens", 0)
    except Exception:
        logger.exception("Failed to generate result message")

    with transaction.atomic():
        attempt.answers.all().delete()

        answer_objects = []
        for ad in answers_to_create:
            answer_objects.append(
                attempt.answers.model(
                    attempt=attempt,
                    question=ad["question"],
                    selected_option_id=ad["selected_option_id"],
                    open_ended_text=ad["open_ended_text"],
                    is_correct=ad["is_correct"],
                    points_earned=ad["points_earned"],
                    ai_evaluation=ad["ai_evaluation"],
                )
            )
        attempt.answers.model.objects.bulk_create(answer_objects)

        attempt.status = TestAttempt.Status.COMPLETED
        attempt.score_percentage = score_pct
        attempt.total_points = total_points
        attempt.earned_points = earned_points
        attempt.passed = passed
        attempt.input_tokens = total_input_tokens
        attempt.output_tokens = total_output_tokens
        attempt.thinking_tokens = total_thinking_tokens
        attempt.result_message = result_msg
        attempt.strengths = strengths
        attempt.weaknesses = weaknesses
        attempt.save()

        if passed and attempt.resume_id:
            resume_skill, created = ResumeSkill.objects.get_or_create(
                resume=attempt.resume,
                skill=attempt.test.skill,
                defaults={
                    "proficiency_level": attempt.test.target_level,
                    "is_verified": True,
                    "verified_at": timezone.now(),
                    "verified_test_attempt": attempt,
                },
            )
            if not created:
                resume_skill.is_verified = True
                resume_skill.verified_at = timezone.now()
                resume_skill.verified_test_attempt = attempt
                resume_skill.save(update_fields=[
                    "is_verified", "verified_at", "verified_test_attempt"
                ])

        if passed and attempt.roadmap_item_id:
            roadmap_item = attempt.roadmap_item
            roadmap_item.status = RoadmapItem.Status.VERIFIED
            roadmap_item.save(update_fields=["status", "updated_at"])

        if passed and attempt.vacancy_roadmap_item_id:
            vr_item = attempt.vacancy_roadmap_item
            vr_item.status = VacancyRoadmapItem.Status.VERIFIED
            vr_item.save(update_fields=["status", "updated_at"])

        if passed and attempt.resume_id:
            from apps.student_analytics.models import StudentAnalytics
            analytics = StudentAnalytics.objects.filter(
                candidate=attempt.candidate,
            ).select_for_update().first()
            if analytics:
                verified_count = ResumeSkill.objects.filter(
                    resume=attempt.resume,
                    is_verified=True,
                ).count()
                analytics.verified_skills_count = verified_count
                total_items = analytics.total_roadmap_skills
                progress_pct = round(verified_count / total_items * 100, 1) if total_items else 0
                analytics.track_progress_percentage = progress_pct
                analytics.save(update_fields=[
                    "verified_skills_count",
                    "track_progress_percentage",
                    "updated_at",
                ])

    return attempt
