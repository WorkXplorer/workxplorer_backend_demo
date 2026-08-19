import logging

from apps.ai.services.ai_utils import parse_json_response
from apps.skills.localization import LANGUAGE_DISPLAY_NAMES
from utils.prompt_sanitizer import sanitize_prompt_value

logger = logging.getLogger(__name__)


def analyze_strengths_weaknesses(ai_client, skill_name, category_scores, language):
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")
    skill_name = sanitize_prompt_value(skill_name)

    formatted_scores = "\n".join(
        f"  {cat}: {info['earned']}/{info['total']} ({round(info['earned']/info['total']*100) if info['total'] else 0}%)"
        for cat, info in category_scores.items()
    )

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a skill assessment analyst. Respond in {lang_name}. "
                "Analyze test results and categorize sub-competencies into strengths and weaknesses. "
                "Return JSON with 'strengths' and 'weaknesses' arrays."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Skill: {skill_name}\n"
                f"Category scores:\n{formatted_scores}\n\n"
                "For each category, provide a short human-readable description. "
                "Categories with >= 60% score are strengths, < 60% are weaknesses. "
                "Respond in JSON: "
                '{"strengths": [{"category": "...", "description": "..."}], '
                '"weaknesses": [{"category": "...", "description": "..."}]}'
            ),
        },
    ]

    response = ai_client.cached_completion(
        messages,
        "test_analysis",
        skill_name,
        language,
        formatted_scores,
        temperature=0.2,
        json_mode=True,
    )

    content = response["choices"][0]["message"]["content"]
    usage = response.get("usage", {})
    return parse_json_response(content), usage


def generate_result_message(ai_client, score, passed, skill_name, language):
    lang_name = LANGUAGE_DISPLAY_NAMES.get(language, "English")
    skill_name = sanitize_prompt_value(skill_name)

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a supportive career coach. Respond in {lang_name}. "
                "Generate a short, personalized message (1-2 sentences) for a test result."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Skill: {skill_name}\n"
                f"Score: {score}%\n"
                f"Passed: {passed}\n\n"
                "Generate the result message."
            ),
        },
    ]

    response = ai_client.cached_completion(
        messages,
        "test_result_msg",
        skill_name,
        str(score),
        str(passed),
        language,
        temperature=0.3,
    )

    usage = response.get("usage", {})
    return response["choices"][0]["message"]["content"].strip(), usage
