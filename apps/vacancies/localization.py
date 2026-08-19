TRANSLATIONS = {
    "employment_type": {
        "uz": {
            "FULL_TIME": "To'liq ish kuni",
            "PART_TIME": "Qisman ish kuni",
            "CONTRACT": "Shartnoma asosida",
            "INTERNSHIP": "Stajirovka",
        },
        "ru": {
            "FULL_TIME": "Полная занятость",
            "PART_TIME": "Частичная занятость",
            "CONTRACT": "Контракт",
            "INTERNSHIP": "Стажировка",
        },
        "en": {
            "FULL_TIME": "Full Time",
            "PART_TIME": "Part Time",
            "CONTRACT": "Contract",
            "INTERNSHIP": "Internship",
        },
    },
    "employment_format": {
        "uz": {
            "ON_SITE": "Ofisda",
            "REMOTE": "Masofadan",
            "HYBRID": "Gibrid",
        },
        "ru": {
            "ON_SITE": "Офис",
            "REMOTE": "Удаленно",
            "HYBRID": "Гибрид",
        },
        "en": {
            "ON_SITE": "On-site",
            "REMOTE": "Remote",
            "HYBRID": "Hybrid",
        },
    },
    "salary_currency": {
        "uz": {
            "USD": "AQSh dollari",
            "UZS": "O'zbekiston so'mi",
            "EUR": "Yevro",
        },
        "ru": {
            "USD": "Доллар США",
            "UZS": "Узбекский сум",
            "EUR": "Евро",
        },
        "en": {
            "USD": "USD",
            "UZS": "UZS",
            "EUR": "EUR",
        },
    },
}


def normalize_language(language: str) -> str:
    normalized_language = (language or "").strip().lower().replace("_", "-")
    lang = normalized_language.split("-")[0] if normalized_language else "en"
    if lang not in TRANSLATIONS["employment_type"]:
        return "en"
    return lang


def get_localized_choices(language: str) -> dict:
    lang = normalize_language(language)
    return {
        "employment_type": TRANSLATIONS["employment_type"].get(
            lang, TRANSLATIONS["employment_type"]["en"]
        ),
        "employment_format": TRANSLATIONS["employment_format"].get(
            lang, TRANSLATIONS["employment_format"]["en"]
        ),
        "salary_currency": TRANSLATIONS["salary_currency"].get(
            lang, TRANSLATIONS["salary_currency"]["en"]
        ),
    }


def add_labels_to_vacancy_data(data: dict, language: str) -> dict:
    choices = get_localized_choices(language)

    data["employment_type_display"] = choices["employment_type"].get(
        data.get("employment_type"), data.get("employment_type")
    )
    data["employment_format_display"] = choices["employment_format"].get(
        data.get("employment_format"), data.get("employment_format")
    )
    data["salary_currency_display"] = choices["salary_currency"].get(
        data.get("salary_currency"), data.get("salary_currency")
    )

    return data