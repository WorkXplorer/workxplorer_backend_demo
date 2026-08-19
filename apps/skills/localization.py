import re

from django.db.models import Q

from apps.skills.models import Skill
from utils.language import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


def normalize_language(language: str | None) -> str:
    language = (language or "").strip().lower().replace("_", "-")
    language = language.split("-")[0] if language else ""
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def user_preferred_language(user=None) -> str:
    """
    Resolve the user's preferred language with the following priority:
      1. Accept-Language HTTP header (if explicitly set to a non-default language)
      2. User's stored preferred_language in the database
      3. Fall back to get_request_language() -> DEFAULT_LANGUAGE ("uz")

    Since Django's LANGUAGE_CODE is "en", we can distinguish an explicit
    Accept-Language header from the absence of one: if get_language()
    returns "uz" or "ru", it was definitely sent by the client.
    """
    from django.conf import settings
    from django.utils.translation import get_language

    raw_lang = get_language()
    if raw_lang:
        raw_lang = raw_lang.split("-")[0].lower()

    default_code = settings.LANGUAGE_CODE.split("-")[0].lower()

    # If the request language was explicitly set via Accept-Language
    # (i.e. it differs from LANGUAGE_CODE), it takes highest priority.
    if raw_lang in SUPPORTED_LANGUAGES and raw_lang != default_code:
        return raw_lang

    # Fall back to the user's stored database preference.
    user_lang = getattr(user, "preferred_language", None)
    if user_lang:
        return normalize_language(user_lang)

    # Final fallback: the activated request language or the platform default.
    return normalize_language(raw_lang)


def localized_skill_name(skill: Skill, language: str | None = None) -> str:
    language = normalize_language(language)
    values = [
        getattr(skill, f"name_{language}", None),
        getattr(skill, "name_en", None),
        getattr(skill, "name_ru", None),
        getattr(skill, "name_uz", None),
        getattr(skill, "name", None),
    ]
    for value in values:
        value = str(value or "").strip()
        if value:
            return value
    return ""


def skill_name_query(skill_name: str) -> Q:
    return (
        Q(name__iexact=skill_name)
        | Q(name_en__iexact=skill_name)
        | Q(name_ru__iexact=skill_name)
        | Q(name_uz__iexact=skill_name)
    )


def find_skill_by_any_name(skill_name: str) -> Skill | None:
    skill_name = str(skill_name or "").strip()
    if not skill_name:
        return None

    skill = Skill.objects.filter(skill_name_query(skill_name)).order_by("id").distinct().first()
    if skill:
        return skill

    from apps.skills.models import SkillSynonym

    synonym = SkillSynonym.objects.filter(synonym__iexact=skill_name).select_related("skill").first()
    if synonym:
        return synonym.skill

    skill = Skill.objects.filter(
        Q(name__icontains=skill_name)
        | Q(name_en__icontains=skill_name)
        | Q(name_ru__icontains=skill_name)
        | Q(name_uz__icontains=skill_name)
    ).order_by("id").distinct().first()
    if skill:
        return skill

    return None


def skill_create_kwargs(skill_name: str, language: str | None = None) -> dict:
    skill_name = str(skill_name or "").strip()
    language = normalize_language(language)
    return {
        "name": skill_name,
        f"name_{language}": skill_name,
    }


# ---------------------------------------------------------------------------
# Text processing utilities shared across skill recommendation & market sync
# ---------------------------------------------------------------------------

def clean_text(text):
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def normalize_text(text):
    text = clean_text(text).lower()
    return re.sub(r"[^0-9a-zа-яёғқҳўүіїєçşöüğ'#+.\- ]+", " ", text).strip()


def normalized_key(text):
    return re.sub(r"\s+", " ", normalize_text(text))


LANGUAGE_DISPLAY_NAMES = {"uz": "Uzbek", "ru": "Russian", "en": "English"}

LANGUAGE_LEVELS = {"a1", "a2", "b1", "b2", "c1", "c2"}


LANGUAGE_SKILL_ALIASES = {
    "русский": "language:ru",
    "русский язык": "language:ru",
    "russian": "language:ru",
    "russian language": "language:ru",
    "английский": "language:en",
    "английский язык": "language:en",
    "english": "language:en",
    "english language": "language:en",
    "узбекский": "language:uz",
    "узбекский язык": "language:uz",
    "uzbek": "language:uz",
    "uzbek language": "language:uz",
}


def clean_market_skill_name(skill_name):
    skill_name = clean_text(skill_name)
    if not skill_name:
        return ""

    parts = re.split(r"\s+[—–-]\s+", skill_name)
    if len(parts) >= 2 and clean_text(parts[1]).lower() in LANGUAGE_LEVELS:
        return clean_text(parts[0])

    match = re.match(
        r"^(?P<name>.+?)\s+(?P<level>A1|A2|B1|B2|C1|C2)\b.*$",
        skill_name,
        flags=re.IGNORECASE,
    )
    if match:
        possible_name = clean_text(match.group("name"))
        if normalized_key(possible_name) in LANGUAGE_SKILL_ALIASES:
            return possible_name

    return skill_name


def canonical_market_skill_key(skill_name):
    key = normalized_key(clean_market_skill_name(skill_name))
    return LANGUAGE_SKILL_ALIASES.get(key, key)


def unique_items(items):
    result = []
    seen = set()
    for item in items:
        item = clean_text(item)
        key = normalized_key(item)
        if item and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def split_requirement_text(text):
    from bs4 import BeautifulSoup

    if not text:
        return []

    soup = BeautifulSoup(str(text), "html.parser")
    plain = clean_text(soup.get_text(" ", strip=True))
    if not plain:
        return []

    parts = re.split(r"\s*[;•]\s*|\s+\-\s+|\n+|\.\s+", plain)
    return unique_items(part for part in parts if len(clean_text(part)) >= 3)
