import logging
import re
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _lazy

logger = logging.getLogger(__name__)

VARIABLE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

VARIABLE_CANDIDATE_NAME = "candidate_name"
VARIABLE_POSITION = "position"
VARIABLE_COMPANY_NAME = "company_name"
VARIABLE_SALARY = "salary"
VARIABLE_START_DATE = "start_date"
VARIABLE_HR_NAME = "hr_name"

ALL_VARIABLES = frozenset({
    VARIABLE_CANDIDATE_NAME,
    VARIABLE_POSITION,
    VARIABLE_COMPANY_NAME,
    VARIABLE_SALARY,
    VARIABLE_START_DATE,
    VARIABLE_HR_NAME,
})

# Russian forms use a CamelCase Cyrillic style to match the HR templates design.
# English/Uzbek forms keep the snake_case convention.
VARIABLE_LOCALIZATION = {
    VARIABLE_CANDIDATE_NAME: {
        "en": "{{candidate_name}}",
        "uz": "{{nomzod_ismi}}",
        "ru": "{{ИмяКандидата}}",
    },
    VARIABLE_POSITION: {
        "en": "{{position}}",
        "uz": "{{lavozim}}",
        "ru": "{{Позиция}}",
    },
    VARIABLE_COMPANY_NAME: {
        "en": "{{company_name}}",
        "uz": "{{kompaniya_nomi}}",
        "ru": "{{Компания}}",
    },
    VARIABLE_SALARY: {
        "en": "{{salary}}",
        "uz": "{{maosh}}",
        "ru": "{{Зарплата}}",
    },
    VARIABLE_START_DATE: {
        "en": "{{start_date}}",
        "uz": "{{boshlanish_sanasi}}",
        "ru": "{{ДатаНачала}}",
    },
    VARIABLE_HR_NAME: {
        "en": "{{hr_name}}",
        "uz": "{{hr_ismi}}",
        "ru": "{{ИмяHR}}",
    },
}

# Legacy / alternative forms that must still resolve to a canonical variable
# (e.g. older Russian snake_case forms saved before the design refresh).
VARIABLE_ALIASES = {
    "{{имя_кандидата}}": VARIABLE_CANDIDATE_NAME,
    "{{должность}}": VARIABLE_POSITION,
    "{{название_компании}}": VARIABLE_COMPANY_NAME,
}

_REVERSE_MAP = {}
for canonical, translations in VARIABLE_LOCALIZATION.items():
    for lang, template_form in translations.items():
        key = template_form.lower()
        if key in _REVERSE_MAP and _REVERSE_MAP[key] != canonical:
            raise ValueError(
                f"Collision in _REVERSE_MAP: '{key}' maps to both "
                f"'{_REVERSE_MAP[key]}' and '{canonical}'"
            )
        _REVERSE_MAP[key] = canonical

for alias_form, canonical in VARIABLE_ALIASES.items():
    key = alias_form.lower()
    if key in _REVERSE_MAP and _REVERSE_MAP[key] != canonical:
        raise ValueError(
            f"Collision in _REVERSE_MAP for alias '{key}': maps to both "
            f"'{_REVERSE_MAP[key]}' and '{canonical}'"
        )
    _REVERSE_MAP[key] = canonical


def extract_variables(text, max_vars=100):
    matches = VARIABLE_PATTERN.findall(text)
    if len(matches) > max_vars:
        logger.warning(
            "Text contains %d template variables, truncating to %d",
            len(matches), max_vars,
        )
        matches = matches[:max_vars]
    return {m.lower() for m in matches}


def normalize_variable(raw_name):
    template_form = "{{" + raw_name.lower() + "}}"
    return _REVERSE_MAP.get(template_form, raw_name.lower())


def get_unknown_variables(text):
    raw_names = extract_variables(text)
    unknown = set()
    for raw in raw_names:
        canonical = normalize_variable(raw)
        if canonical not in ALL_VARIABLES:
            unknown.add(raw)
    return unknown


def get_used_variables(text):
    raw_names = extract_variables(text)
    used = set()
    for raw in raw_names:
        canonical = normalize_variable(raw)
        if canonical in ALL_VARIABLES:
            used.add(canonical)
    return used


VARIABLE_INFO = [
    {
        "key": VARIABLE_CANDIDATE_NAME,
        "description": _lazy("Candidate's full name."),
    },
    {
        "key": VARIABLE_POSITION,
        "description": _lazy("Job position / vacancy title."),
    },
    {
        "key": VARIABLE_COMPANY_NAME,
        "description": _lazy("Company name."),
    },
    {
        "key": VARIABLE_SALARY,
        "description": _lazy("Salary / compensation for the position."),
    },
    {
        "key": VARIABLE_START_DATE,
        "description": _lazy("Proposed start date."),
    },
    {
        "key": VARIABLE_HR_NAME,
        "description": _lazy("Name of the recruiter / HR sending the message."),
    },
]


def get_localized_form(canonical_variable, lang="en"):
    translations = VARIABLE_LOCALIZATION.get(canonical_variable, {})
    return translations.get(lang) or translations.get("en", f"{{{{{canonical_variable}}}}}")


def _format_salary(vacancy):
    """Build a human-readable salary string from the vacancy, or '' if absent."""
    salary_min = getattr(vacancy, "salary_min", None)
    salary_max = getattr(vacancy, "salary_max", None)
    currency = getattr(vacancy, "salary_currency", "") or ""

    def _fmt(value):
        # Drop trailing decimals for whole numbers (e.g. 7000000.00 -> 7000000)
        try:
            return f"{int(value):,}".replace(",", " ")
        except (TypeError, ValueError):
            return str(value)

    if salary_min and salary_max:
        amount = f"{_fmt(salary_min)} – {_fmt(salary_max)}"
    elif salary_min:
        amount = _fmt(salary_min)
    elif salary_max:
        amount = _fmt(salary_max)
    else:
        return ""

    return f"{amount} {currency}".strip()


def render_template_variables(
    text, candidate, vacancy, company, hr_name=None, start_date=None
):
    try:
        profile = candidate.candidateprofile
    except ObjectDoesNotExist:
        profile = None

    if profile and profile.full_name:
        candidate_name = profile.full_name
    else:
        logger.warning(
            "Candidate %s has no full_name set; using placeholder for template variable",
            candidate.id,
        )
        candidate_name = "[Candidate Name Not Set]"

    position = vacancy.title
    company_name = company.name

    value_map = {
        VARIABLE_CANDIDATE_NAME: escape(candidate_name),
        VARIABLE_POSITION: escape(position),
        VARIABLE_COMPANY_NAME: escape(company_name),
    }

    salary = _format_salary(vacancy)
    if salary:
        value_map[VARIABLE_SALARY] = escape(salary)

    if hr_name:
        value_map[VARIABLE_HR_NAME] = escape(str(hr_name))

    if start_date:
        value_map[VARIABLE_START_DATE] = escape(str(start_date))

    def replace_var(match):
        raw_name = match.group(1)
        canonical = normalize_variable(raw_name)
        return value_map.get(canonical, match.group(0))

    return VARIABLE_PATTERN.sub(replace_var, text)


render_invitation_text = render_template_variables
