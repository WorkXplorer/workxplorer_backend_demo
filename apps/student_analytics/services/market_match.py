import logging

from django.utils import timezone

from apps.ai.services import AIProviderClient
from apps.general.services.skill_recommendation import (
    build_candidate_domain_skills_payload,
    get_candidate_resume,
)
from apps.general.services.market_skill_cache import collect_hh_market_skills_with_cache
from apps.general.services.hh_aliases import candidate_hh_search_query_variants
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES, user_preferred_language

from apps.student_analytics.models import StudentAnalytics
from utils.prompt_sanitizer import sanitize_prompt_list, sanitize_prompt_value

logger = logging.getLogger(__name__)


def compute_market_match_percentage(existing_skills, missing_skills):
    total = len(existing_skills) + len(missing_skills)
    if total == 0:
        return 0.0
    return round(len(existing_skills) / total * 100, 1)


def generate_market_match_insight(ai_client, match_percentage, target_role, strong_skills, weak_skills, language):
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")

    target_role = sanitize_prompt_value(target_role)
    strong_skills = sanitize_prompt_list(strong_skills[:5])
    weak_skills = sanitize_prompt_list(weak_skills[:5])

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a career advisor. Respond in {lang_name}. "
                "Generate a concise, encouraging insight paragraph (2-3 sentences) "
                "explaining the candidate's market match and suggesting which skills to improve."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Target role: {target_role}\n"
                f"Market match: {match_percentage}%\n"
                f"Strong skills: {', '.join(strong_skills) or 'None'}\n"
                f"Weak/missing skills: {', '.join(weak_skills) or 'None'}\n\n"
                "Generate the insight text."
            ),
        },
    ]

    response = ai_client.cached_completion(
        messages,
        "market_match_insight",
        str(match_percentage),
        target_role,
        language,
        ",".join(strong_skills),
        ",".join(weak_skills),
        temperature=0.3,
        json_mode=False,
    )

    content = response["choices"][0]["message"]["content"]
    return content.strip(), response


def compute_or_refresh_analytics(candidate, resume_id=None, ai_model="default"):
    resume = get_candidate_resume(candidate, resume_id)
    if not resume:
        return None

    language = user_preferred_language(candidate)
    target_role = resume.position or resume.title or (resume.domain.name if resume.domain else "")

    market_query = target_role
    query_variants = candidate_hh_search_query_variants(resume, market_query, title_query=market_query)

    market_skills, _, _, market_vacancy_count = collect_hh_market_skills_with_cache(
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

    skill_payload = build_candidate_domain_skills_payload(
        resume,
        market_skills=market_skills,
        language=language,
        skill_limit=30,
        aggregate=True,
    )

    existing_skills = skill_payload.get("existing_skills", [])
    missing_skills = skill_payload.get("missing_skills", [])
    match_pct = compute_market_match_percentage(existing_skills, missing_skills)

    strong_skill_names = [s["skill_name"] for s in existing_skills[:5]]
    weak_skill_names = [s["skill_name"] for s in missing_skills[:5]]

    strong_skills_data = [
        {"skill_name": s["skill_name"], "level": s.get("proficiency_level", "UNDEFINED")}
        for s in existing_skills[:5]
    ]
    weak_skills_data = [
        {"skill_name": s["skill_name"], "level": s.get("proficiency_level", "UNDEFINED")}
        for s in missing_skills[:5]
    ]

    ai_client = AIProviderClient()
    insight_text = ""
    input_tok = 0
    output_tok = 0
    thinking_tok = 0
    try:
        insight_text, insight_response = generate_market_match_insight(
            ai_client, match_pct, target_role, strong_skill_names, weak_skill_names, language
        )
        usage = insight_response.get("usage", {})
        input_tok = usage.get("prompt_tokens", 0)
        output_tok = usage.get("completion_tokens", 0)
        thinking_tok = usage.get("thinking_tokens", 0)
    except Exception:
        logger.exception("Failed to generate market match insight")

    analytics, _ = StudentAnalytics.objects.update_or_create(
        candidate=candidate,
        defaults={
            "resume": resume,
            "target_role": target_role,
            "market_match_percentage": match_pct,
            "market_match_insight": insight_text,
            "strong_skills": strong_skills_data,
            "skills_to_improve": weak_skills_data,
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "thinking_tokens": thinking_tok,
            "last_computed_at": timezone.now(),
        },
    )

    return analytics
