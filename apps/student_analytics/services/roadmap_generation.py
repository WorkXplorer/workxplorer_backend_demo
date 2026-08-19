import logging
import re

from django.core.cache import cache as django_cache
from django.db import DataError, IntegrityError, transaction
from django.utils import timezone
from django.utils.html import strip_tags

from apps.ai.services import GroqClient
from apps.ai.services.ai_utils import parse_json_response
from apps.general.services.skill_recommendation import get_candidate_resume
from apps.general.services.market_skill_cache import collect_hh_market_skills_with_cache
from apps.general.services.hh_aliases import candidate_hh_search_query_variants
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES, find_skill_by_any_name, user_preferred_language
from apps.skills.models import Skill
from apps.student_analytics.models import SkillRoadmap, RoadmapItem, StudentAnalytics
from utils.prompt_sanitizer import sanitize_prompt_list, sanitize_prompt_value

logger = logging.getLogger(__name__)

_MAX_SKILL_NAME_LENGTH = 100
# ponytail: '/' and '&' allowed for real skill names (C++, R&D);
# if ever used in file paths, validate separately.
_VALID_SKILL_NAME_RE = re.compile(
    r"^[a-zA-Z0-9\u0400-\u04FF\u040E\u045E\u0490-\u04FF'#+.\-&/() ]+$"
)
_TRANSLATION_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days


def _sanitize_skill_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return ""
    if len(name) > _MAX_SKILL_NAME_LENGTH:
        name = name[:_MAX_SKILL_NAME_LENGTH]
    if not _VALID_SKILL_NAME_RE.match(name):
        name = re.sub(r"[^a-zA-Z0-9\u0400-\u04FF'#+.\-&/() ]", "", name).strip()
    return name


def _sanitize_translation_value(val: object, skill_name: str) -> str:
    if not isinstance(val, str):
        return skill_name
    val = strip_tags(val)
    val = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\ufeff]", "", val)
    val = re.sub(r"[*_~`]", "", val)
    val = val.strip()
    if not val:
        return skill_name
    if len(val) > _MAX_SKILL_NAME_LENGTH:
        val = val[:_MAX_SKILL_NAME_LENGTH]
    return val


def _translate_skill_name(skill_name: str) -> dict[str, str]:
    skill_name = _sanitize_skill_name(skill_name)
    if not skill_name:
        return {"en": "", "ru": "", "uz": ""}

    translations = {"en": skill_name, "ru": skill_name, "uz": skill_name}

    cache_key = f"skill_translation:{skill_name.lower()}"
    cached = django_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        client = GroqClient()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional translator. Translate the given skill name "
                    "into English, Russian, and Uzbek. Return ONLY a raw JSON object "
                    "with keys 'en', 'ru', 'uz'. No markdown, no explanations."
                ),
            },
            {
                "role": "user",
                "content": f"Translate this skill name: {skill_name}",
            },
        ]
        response = client.cached_completion(
            messages,
            "skill_translate",
            skill_name.lower(),
            temperature=0.0,
            json_mode=True,
        )
        content = response["choices"][0]["message"]["content"]
        parsed = parse_json_response(content)
        if isinstance(parsed, dict):
            for lang in ("en", "ru", "uz"):
                val = parsed.get(lang)
                sanitized = _sanitize_translation_value(val, skill_name)
                if sanitized:
                    translations[lang] = sanitized

        django_cache.set(cache_key, translations, timeout=_TRANSLATION_CACHE_TTL)
        logger.info("Translated skill name '%s' -> en=%s ru=%s uz=%s",
                     skill_name, translations["en"], translations["ru"], translations["uz"])
    except Exception:
        logger.warning("Failed to translate skill name '%s', using original", skill_name)

    return translations


def _resolve_or_create_skill(skill_name: str, language: str = "uz") -> Skill:
    skill_name = _sanitize_skill_name(skill_name)
    if not skill_name:
        raise ValueError("skill_name is empty after sanitization")

    skill = find_skill_by_any_name(skill_name)
    if skill:
        return skill

    language = (language or "uz").lower()[:2]
    if language not in ("uz", "ru", "en"):
        language = "uz"

    translations = _translate_skill_name(skill_name)
    name_en = _sanitize_translation_value(translations["en"], skill_name)
    name_ru = _sanitize_translation_value(translations["ru"], skill_name)
    name_uz = _sanitize_translation_value(translations["uz"], skill_name)

    try:
        with transaction.atomic():
            skill = Skill.objects.create(
                name_en=name_en,
                name_ru=name_ru,
                name_uz=name_uz,
                is_active=True,
            )
    except (IntegrityError, DataError):
        pass
    else:
        logger.info(
            "Auto-created skill id=%s name=%s (lang=%s) en=%s ru=%s uz=%s",
            skill.id, skill_name, language,
            name_en, name_ru, name_uz,
        )
        return skill

    try:
        with transaction.atomic():
            skill = Skill.objects.create(
                name_en=skill_name,
                name_ru=skill_name,
                name_uz=skill_name,
                is_active=True,
            )
    except (IntegrityError, DataError):
        skill = find_skill_by_any_name(skill_name)
        if not skill:
            logger.error(
                "Critical: unable to create or find skill '%s' after fallback",
                skill_name,
            )
            raise
        logger.info(
            "Race condition resolved: using concurrently created skill id=%s name=%s",
            skill.id, skill_name,
        )
    else:
        logger.warning(
            "Auto-created skill id=%s name=%s with fallback names (translation conflicted)",
            skill.id, skill_name,
        )

    return skill


def _build_current_skills_payload(resume):
    skills = []
    for rs in resume.resume_skills.select_related("skill").all():
        skill_name = rs.skill.name if rs.skill else ""
        skills.append({
            "name": skill_name,
            "level": rs.proficiency_level or "UNDEFINED",
            "status": "verified" if rs.is_verified else "not_verified",
        })
    return skills


def _build_market_demand_payload(market_skills):
    demand = {}
    for ms in (market_skills or []):
        name = ms.get("skill_name", "")
        if name:
            demand[name] = {
                "vacancy_count": ms.get("vacancy_count", 0),
            }
    return demand


def generate_roadmap(candidate, resume_id=None, ai_model="groq"):
    resume = get_candidate_resume(candidate, resume_id)
    if not resume:
        return None

    language = user_preferred_language(candidate)
    target_role = resume.position or resume.title or (resume.domain.name if resume.domain else "")

    current_skills = _build_current_skills_payload(resume)

    market_query = target_role
    query_variants = candidate_hh_search_query_variants(resume, market_query, title_query=market_query)
    market_skills, _, _, _ = collect_hh_market_skills_with_cache(
        query=market_query,
        area_id="97",
        max_pages=3,
        per_page=20,
        language=language,
        domain=resume.domain,
        prefer_cache=True,
        refresh_cache=False,
        query_variants=query_variants,
        cache_query_variants=query_variants,
        aggregate_mode=True,
    )
    market_demand = _build_market_demand_payload(market_skills)

    missing_skill_names = []
    current_names = {s["name"].lower() for s in current_skills}
    for ms in (market_skills or []):
        name = ms.get("skill_name", "")
        if name and name.lower() not in current_names:
            missing_skill_names.append(name)
    missing_skill_names = missing_skill_names[:10]

    target_role = sanitize_prompt_value(target_role)
    missing_skill_names = sanitize_prompt_list(missing_skill_names)
    for skill in current_skills:
        skill["name"] = sanitize_prompt_value(skill["name"])
        skill["level"] = sanitize_prompt_value(skill.get("level", ""))
        skill["status"] = sanitize_prompt_value(skill.get("status", ""))

    ai_client = GroqClient()

    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")

    messages = [
        {
            "role": "system",
            "content": (
                f"You are an expert career path designer. Respond in {lang_name}. "
                "Generate an ordered skill roadmap from the candidate's current level to the target role. "
                "Return JSON with a 'roadmap' array of objects."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Target role: {target_role}\n"
                f"Current skills: {current_skills}\n"
                f"Missing skills: {missing_skill_names}\n"
                f"Market demand: {market_demand}\n\n"
                "Generate a roadmap of 3-7 skills in optimal learning order. "
                "For each skill provide:\n"
                "- skill_name (string)\n"
                "- target_level (BEGINNER/INTERMEDIATE/ADVANCED/EXPERT)\n"
                "- is_critical (boolean)\n"
                "- impact_percentage (integer 5-30, estimated impact on hire chances)\n"
                f"- context_message (2-3 sentences in {lang_name}: where this skill is used in real work, "
                "why it matters for the target role, what problems it solves)\n"
                "- salary_impact_percentage (integer 0-30, estimated salary increase with this skill)\n"
                "- learning_time_hours (integer 10-200, estimated hours to reach target level from current level)\n"
                "- reasoning (short string, why this skill is important)\n\n"
                "Respond in JSON."
            ),
        },
    ]

    roadmap_input_tokens = 0
    roadmap_output_tokens = 0
    roadmap_thinking_tokens = 0
    try:
        response = ai_client.chat_completion(messages, temperature=0.3, json_mode=True)
        usage = response.get("usage", {})
        roadmap_input_tokens = usage.get("prompt_tokens", 0)
        roadmap_output_tokens = usage.get("completion_tokens", 0)
        roadmap_thinking_tokens = usage.get("thinking_tokens", 0)
        content = response["choices"][0]["message"]["content"]
        parsed = parse_json_response(content)
    except Exception:
        logger.exception("Failed to generate roadmap via AI")
        return None
    roadmap_data = parsed.get("roadmap", [])

    with transaction.atomic():
        analytics = StudentAnalytics.objects.select_for_update().filter(
            candidate=candidate,
        ).first()
        if analytics is None:
            analytics = StudentAnalytics.objects.create(
                candidate=candidate,
                resume=resume,
                target_role=target_role,
            )

        SkillRoadmap.objects.filter(analytics=analytics).delete()

        roadmap = SkillRoadmap.objects.create(
            analytics=analytics,
            target_role=target_role,
            ai_model=ai_model,
            input_tokens=roadmap_input_tokens,
            output_tokens=roadmap_output_tokens,
            thinking_tokens=roadmap_thinking_tokens,
        )

        for idx, item in enumerate(roadmap_data, start=1):
            skill_name = item.get("skill_name", "")
            skill = _resolve_or_create_skill(skill_name, language)

            current_level = "UNDEFINED"
            item_status = RoadmapItem.Status.NOT_STARTED
            for cs in current_skills:
                if cs["name"].lower() == skill_name.lower():
                    current_level = cs["level"]
                    if cs["status"] == "verified":
                        item_status = RoadmapItem.Status.VERIFIED
                    else:
                        item_status = RoadmapItem.Status.IN_PROGRESS
                    break

            learning_hours = item.get("learning_time_hours", 0) or 0

            RoadmapItem.objects.create(
                roadmap=roadmap,
                skill=skill,
                skill_name=skill_name,
                order=idx,
                target_level=item.get("target_level", "INTERMEDIATE"),
                current_level=current_level,
                status=item_status,
                is_critical=bool(item.get("is_critical", False)),
                impact_percentage=item.get("impact_percentage", 0),
                vacancy_count=market_demand.get(skill_name, {}).get("vacancy_count", 0),
                context_message=item.get("context_message", ""),
                salary_impact_percentage=item.get("salary_impact_percentage", 0),
                learning_time_hours=learning_hours,
                learning_time_weeks=max(1, round(learning_hours / 40)) if learning_hours else 0,
            )

        total_items = roadmap.items.count()
        verified_count = roadmap.items.filter(status=RoadmapItem.Status.VERIFIED).count()
        progress_pct = round(verified_count / total_items * 100, 1) if total_items else 0

        analytics.total_roadmap_skills = total_items
        analytics.track_progress_percentage = progress_pct
        analytics.verified_skills_count = verified_count
        analytics.last_computed_at = timezone.now()
        analytics.save(update_fields=[
            "total_roadmap_skills",
            "track_progress_percentage",
            "verified_skills_count",
            "last_computed_at",
            "updated_at",
        ])

        transaction.on_commit(
            lambda: _enqueue_learning_materials(str(roadmap.id), ai_model, language)
        )

    return roadmap


def _enqueue_learning_materials(roadmap_id, ai_model, language):
    try:
        from apps.skills.tasks import enqueue_learning_materials_generation
        enqueue_learning_materials_generation(roadmap_id, ai_model, language)
    except Exception:
        logger.exception("Failed to enqueue learning materials for roadmap %s", roadmap_id)
