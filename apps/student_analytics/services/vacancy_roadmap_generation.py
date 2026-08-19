import logging

from django.db import transaction
from django.utils.html import strip_tags

from apps.ai.services import AIProviderClient
from apps.ai.services.ai_utils import parse_json_response
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES, user_preferred_language
from apps.student_analytics.models import VacancySkillRoadmap, VacancyRoadmapItem
from apps.student_analytics.services.roadmap_generation import (
    _resolve_or_create_skill,
    _sanitize_skill_name,
)
from utils.prompt_sanitizer import sanitize_prompt_list, sanitize_prompt_value, detect_prompt_injection
from apps.applications.models import EvaluationStatus

logger = logging.getLogger(__name__)


def _build_resume_skills_payload(resume):
    if not resume:
        return []
    skills = []
    for rs in resume.resume_skills.select_related("skill").all():
        skill_name = rs.skill.name if rs.skill else ""
        skills.append({
            "name": skill_name,
            "level": rs.proficiency_level or "UNDEFINED",
            "status": "verified" if rs.is_verified else "not_verified",
        })
    return skills


def generate_vacancy_roadmap(application, ai_model="default"):
    vacancy = application.vacancy
    candidate = application.candidate
    evaluation = getattr(application, "ai_evaluation", None)

    if not evaluation or evaluation.status != EvaluationStatus.COMPLETED:
        logger.warning("No completed AI evaluation for application %s", application.id)
        return None

    # ponytail: defense-in-depth — caller also gates, but check here prevents future misuse
    if evaluation.overall_score is None or evaluation.overall_score >= vacancy.minimum_ai_score:
        logger.warning(
            "Application %s not rejected (score %s >= %s), skipping roadmap",
            application.id, evaluation.overall_score, vacancy.minimum_ai_score,
        )
        return None

    result = evaluation.result or {}
    missing_skills_list = (
        result.get("missing_skills")
        or result.get("skills_analysis", {}).get("missing_skills")
        or []
    )
    if isinstance(missing_skills_list, list):
        missing_skill_names = [
            ms.get("skill_name", ms) if isinstance(ms, dict) else str(ms)
            for ms in missing_skills_list[:10]
        ]
    else:
        missing_skill_names = []

    if not missing_skill_names:
        logger.warning("No missing_skills in AI evaluation for application %s", application.id)
        return None

    resume = application.resume_used
    current_skills = _build_resume_skills_payload(resume)

    language = user_preferred_language(candidate)

    vacancy_title = sanitize_prompt_value(vacancy.title or "")
    vacancy_requirements = sanitize_prompt_value(strip_tags(vacancy.requirements or ""))
    vacancy_description = sanitize_prompt_value(strip_tags(vacancy.about_us or ""))
    missing_skill_names = sanitize_prompt_list(missing_skill_names)
    for skill in current_skills:
        match = detect_prompt_injection(skill.get("name", ""))
        if match:
            logger.warning(
                "Prompt injection detected in resume skill '%s' for application %s: %s",
                skill.get("name", ""), application.id, match,
            )
            return None
        skill["name"] = sanitize_prompt_value(skill["name"])
        skill["level"] = sanitize_prompt_value(skill.get("level", ""))
        skill["status"] = sanitize_prompt_value(skill.get("status", ""))

    # ponytail: reject entire generation on injection; prevents recruiter-controlled input from
    # steering the LLM. Upgrade to per-vacancy flag if false-positive rate becomes measurable.
    for field_name, field_value in [
        ("vacancy_title", vacancy_title),
        ("vacancy_requirements", vacancy_requirements),
        ("vacancy_description", vacancy_description),
    ]:
        match = detect_prompt_injection(field_value)
        if match:
            logger.warning(
                "Prompt injection detected in %s for application %s: %s",
                field_name, application.id, match,
            )
            return None

    for missing_skill in missing_skill_names:
        match = detect_prompt_injection(missing_skill)
        if match:
            logger.warning(
                "Prompt injection detected in missing_skill '%s' for application %s: %s",
                missing_skill, application.id, match,
            )
            return None

    ai_client = AIProviderClient()
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an empathetic career coach who provides constructive, actionable feedback. "
                f"Respond in {lang_name}. Return a JSON object with two keys: "
                f"'rejection_summary' (a dict with uz/ru/en keys, each 2-3 sentences explaining "
                f"why the candidate wasn't selected for THIS SPECIFIC vacancy in a supportive tone, "
                f"mentioning specific skill gaps) and "
                f"'roadmap' (an array covering ONLY the skills listed in the candidate's missing "
                f"skills below, one roadmap entry per missing skill, in priority order — never add "
                f"a skill that isn't in that list, and never pad the array to reach any target count)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Vacancy title: {vacancy_title}\n"
                f"Vacancy requirements: {vacancy_requirements}\n"
                f"Vacancy description: {vacancy_description}\n\n"
                f"Candidate's missing skills (from AI evaluation): {missing_skill_names}\n"
                f"Candidate's current skills: {current_skills}\n\n"
                "Generate a vacancy-specific rejection explanation and a focused skill roadmap.\n\n"
                "rejection_summary: Provide uz, ru, en versions. Each should:\n"
                "- Be specific to THIS vacancy (mention the role/title)\n"
                "- Name 2-3 specific missing skills\n"
                "- Be supportive/constructive in tone\n"
                "- Suggest the roadmap as a path to future success\n\n"
                "roadmap: one entry for EACH skill in the candidate's missing skills list above "
                "(MAXIMUM 5 — if there are more than 5 missing skills, keep only the 5 most "
                "important for this vacancy). Do not include any skill_name that isn't in that "
                "list. Order by importance for THIS vacancy. For each:\n"
                "- skill_name (string, use standard English name)\n"
                "- target_level (BEGINNER/INTERMEDIATE/ADVANCED/EXPERT)\n"
                "- is_critical (boolean)\n"
                "- impact_percentage (integer 5-40, estimated impact on qualifying for this vacancy)\n"
                f"- context_message (2-3 sentences in {lang_name}: why this specific skill matters "
                "for this vacancy, what tasks it enables, how it connects to the job requirements)\n"
                "- learning_time_hours (integer 10-200, estimated hours to reach target level)\n\n"
                "Respond in JSON. No markdown, no explanations outside the JSON."
            ),
        },
    ]

    try:
        response = ai_client.chat_completion(messages, temperature=0.3, json_mode=True)
        usage = response.get("usage", {})
        content = response["choices"][0]["message"]["content"]
        parsed = parse_json_response(content)
    except Exception:
        logger.exception("AI failed to generate vacancy roadmap for application %s", application.id)
        return None

    rejection_summary = parsed.get("rejection_summary", {})
    if not isinstance(rejection_summary, dict):
        rejection_summary = {}
    for lang in ("uz", "ru", "en"):
        if lang not in rejection_summary or not isinstance(rejection_summary[lang], str):
            rejection_summary[lang] = ""

    roadmap_data = parsed.get("roadmap", [])
    if not isinstance(roadmap_data, list):
        roadmap_data = []
    roadmap_data = roadmap_data[:5]

    # ponytail: deduplicate by skill_name to prevent UniqueConstraint violation from AI dupes
    seen_skills = set()
    deduped = []
    for item in roadmap_data:
        name = _sanitize_skill_name(item.get("skill_name", ""))
        if name and name.lower() not in seen_skills:
            seen_skills.add(name.lower())
            deduped.append(item)
    roadmap_data = deduped

    if not roadmap_data:
        logger.warning("AI returned no valid roadmap items for application %s", application.id)
        return None

    with transaction.atomic():
        VacancySkillRoadmap.objects.filter(application=application).delete()

        roadmap = VacancySkillRoadmap.objects.create(
            application=application,
            rejection_summary=rejection_summary,
            ai_model=ai_model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
        )

        created = 0
        for idx, item in enumerate(roadmap_data, start=1):
            skill_name = _sanitize_skill_name(item.get("skill_name", ""))
            if not skill_name:
                continue
            skill = _resolve_or_create_skill(skill_name, language)

            current_level = "UNDEFINED"
            item_status = VacancyRoadmapItem.Status.NOT_STARTED
            for cs in current_skills:
                if cs["name"].lower() == skill_name.lower():
                    current_level = cs["level"]
                    item_status = (
                        VacancyRoadmapItem.Status.VERIFIED
                        if cs["status"] == "verified"
                        else VacancyRoadmapItem.Status.IN_PROGRESS
                    )
                    break

            learning_hours = item.get("learning_time_hours", 0) or 0

            impact_raw = item.get("impact_percentage", 0)
            try:
                impact_percentage = float(impact_raw) if impact_raw is not None else 0
            except (TypeError, ValueError):
                impact_percentage = 0

            VacancyRoadmapItem.objects.create(
                roadmap=roadmap,
                skill=skill,
                skill_name=skill_name,
                order=idx,
                target_level=item.get("target_level", "INTERMEDIATE"),
                current_level=current_level,
                status=item_status,
                is_critical=bool(item.get("is_critical", False)),
                impact_percentage=impact_percentage,
                context_message=item.get("context_message", ""),
                learning_time_hours=learning_hours,
                learning_time_weeks=max(1, round(learning_hours / 40)) if learning_hours else 0,
            )
            created += 1

        if created == 0:
            raise ValueError(
                "No valid roadmap items after sanitization for application %s" % application.id
            )

        transaction.on_commit(
            lambda: _enqueue_vacancy_learning_materials(str(roadmap.id), ai_model, language)
        )

    logger.info(
        "Generated vacancy roadmap %s for application %s with %d skills",
        roadmap.id, application.id, roadmap.items.count(),
    )
    return roadmap


def _enqueue_vacancy_learning_materials(vacancy_roadmap_id, ai_model, language):
    try:
        from apps.skills.tasks import enqueue_vacancy_learning_materials_generation
        enqueue_vacancy_learning_materials_generation(vacancy_roadmap_id, ai_model, language)
    except Exception:
        logger.exception(
            "Failed to enqueue learning materials for vacancy roadmap %s", vacancy_roadmap_id
        )
