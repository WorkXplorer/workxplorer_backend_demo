import logging

from django.db import transaction

from apps.ai.services import AIProviderClient
from apps.ai.services.ai_utils import parse_json_response
from apps.general.services.skill_recommendation import get_candidate_resume
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES, user_preferred_language
from utils.prompt_sanitizer import sanitize_prompt_value

from apps.skill_tests.models import SkillTest, TestQuestion

logger = logging.getLogger(__name__)


def generate_test(skill, target_level="INTERMEDIATE", candidate=None, ai_model="default"):
    language = user_preferred_language(candidate) if candidate else "en"
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")

    skill_description = skill.description or ""
    existing_skills_context = ""
    if candidate:
        resume = get_candidate_resume(candidate)
        if resume:
            skill_names = list(
                resume.resume_skills.select_related("skill")
                .values_list("skill__name", flat=True)[:10]
            )
            if skill_names:
                existing_skills_context = f"Candidate's existing skills: {', '.join(skill_names)}"

    skill_name = sanitize_prompt_value(skill.name)
    skill_description = sanitize_prompt_value(skill_description, max_length=2000)
    existing_skills_context = sanitize_prompt_value(existing_skills_context, max_length=1000)
    # target_level is an internal enum value, not user input — no sanitization needed

    ai_client = AIProviderClient()

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an expert skill assessment designer for the WorkXplorer job platform. "
                f"Respond in {lang_name}. "
                "Generate a skill verification test. Return valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Skill: {skill_name}\n"
                f"Skill description: {skill_description}\n"
                f"Target level: {target_level}\n"
                f"{existing_skills_context}\n\n"
                "Generate exactly 3 questions:\n"
                "- 2 multiple-choice (4 options each, exactly one correct)\n"
                "- 1 open-ended (requires 2-3 sentence answer)\n\n"
                "Each question must test a DIFFERENT sub-competency.\n"
                "Difficulty: 40% intermediate, 40% advanced, 20% expert.\n\n"
                "Respond with JSON:\n"
                "{\n"
                '  "title": "test title",\n'
                '  "time_limit_minutes": 10,\n'
                '  "questions": [\n'
                "    {\n"
                '      "order": 1,\n'
                '      "question_type": "MULTIPLE_CHOICE",\n'
                '      "question_text": "...",\n'
                '      "options": [{"id": "A", "text": "..."}, ...],\n'
                '      "correct_answer": {"option_id": "B"},\n'
                '      "points": 1,\n'
                '      "category": "sub_competency_name",\n'
                '      "explanation": "..."\n'
                "    },\n"
                "    {\n"
                '      "order": 3,\n'
                '      "question_type": "OPEN_ENDED",\n'
                '      "question_text": "...",\n'
                '      "options": [],\n'
                '      "correct_answer": {\n'
                '        "keywords": ["keyword1", "keyword2"],\n'
                '        "rubric": "evaluation criteria",\n'
                '        "sample_answer": "..."\n'
                "      },\n"
                '      "points": 2,\n'
                '      "category": "sub_competency_name",\n'
                '      "explanation": "..."\n'
                "    }\n"
                "  ]\n"
                "}"
            ),
        },
    ]

    response = ai_client.chat_completion(messages, temperature=0.3, json_mode=True)
    content = response["choices"][0]["message"]["content"]
    parsed = parse_json_response(content)
    usage = response.get("usage", {})

    with transaction.atomic():
        test = SkillTest.objects.create(
            skill=skill,
            candidate=candidate,
            target_level=target_level,
            title=parsed.get("title", f"Test: {skill.name}"),
            time_limit_minutes=parsed.get("time_limit_minutes", 10),
            total_questions=len(parsed.get("questions", [])),
            ai_model=ai_model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
        )

        for q_data in parsed.get("questions", []):
            TestQuestion.objects.create(
                test=test,
                order=q_data.get("order", 0),
                question_type=q_data.get("question_type", "MULTIPLE_CHOICE"),
                question_text=q_data.get("question_text", ""),
                options=q_data.get("options", []),
                correct_answer=q_data.get("correct_answer", {}),
                points=q_data.get("points", 1),
                category=q_data.get("category", ""),
                explanation=q_data.get("explanation", ""),
            )

    return test
