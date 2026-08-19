"""
AI drafting of HR message templates.

Given a template section (invitation / interview / rejection) and the
recruiter's company context, asks the configured AI client to draft a short,
ready-to-edit message that already places the available `{{variables}}`.
"""

import logging

from apps.hr_templates.constants import ALL_VARIABLES, get_localized_form

logger = logging.getLogger(__name__)

# Per-section guidance for the model.
SECTION_GUIDANCE = {
    "invitation": (
        "a warm, concrete job invitation (cold reach). Mention the position, "
        "salary and start date. Friendly but professional."
    ),
    "interview": (
        "a friendly interview invitation with the meeting details "
        "(format, time, link). Encouraging tone."
    ),
    "rejection": (
        "a respectful, concise rejection. Kind and human, no excessive detail, "
        "wish the candidate success."
    ),
}

LANGUAGE_NAMES = {
    "ru": "Russian",
    "en": "English",
    "uz": "Uzbek",
}


def draft_template_text(
    client,
    *,
    section: str,
    company_name: str,
    locale: str = "ru",
    instruction: str = "",
) -> str:
    """
    Generate a draft template body.

    Args:
        client: An AI client exposing ``chat_completion`` and
            ``parse_json_response`` (Groq).
        section: One of "invitation", "interview", "rejection".
        company_name: Recruiter's company, woven into the message.
        locale: Target language ("ru" / "en" / "uz").
        instruction: Optional extra instruction from the recruiter.

    Returns:
        The drafted message text (plain text with `{{variables}}`).
    """
    lang = locale if locale in LANGUAGE_NAMES else "ru"
    guidance = SECTION_GUIDANCE.get(section, SECTION_GUIDANCE["invitation"])
    language_name = LANGUAGE_NAMES[lang]

    # Variables the model is allowed to use, in their localized form.
    variable_forms = [get_localized_form(code, lang) for code in sorted(ALL_VARIABLES)]
    variables_str = ", ".join(variable_forms)

    system_prompt = (
        "You are an experienced HR assistant who writes short, polished "
        "recruiting messages. You ALWAYS respond with a single JSON object of "
        'the form {"text": "<message>"} and nothing else. The message must be '
        f"written in {language_name}. "
        "Use ONLY these placeholder variables where appropriate, copied verbatim "
        f"(do not invent new ones): {variables_str}. "
        "Keep it concise (3-6 short sentences), warm and human. Do not include "
        "a subject line. Do not wrap the message in quotes."
    )

    user_prompt = f"Write {guidance}\nCompany name: {company_name or 'the company'}."
    if instruction:
        user_prompt += f"\nAdditional instruction from the recruiter: {instruction}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = client.chat_completion(messages, temperature=0.7, json_mode=True)
    content = response["choices"][0]["message"]["content"]
    data = client.parse_json_response(content)
    text = (data.get("text") or "").strip()

    if not text:
        raise ValueError("AI returned an empty template draft.")

    return text
