import re

UZ_PHONE_RE = re.compile(r"^\+998\d{9}$")


class InvalidPhoneNumber(ValueError):
    pass


def normalize_uz_phone(raw: str) -> str:
    """
    Normalizes a user-entered Uzbekistan phone number to canonical
    +998XXXXXXXXX form. Accepts "901234567", "998901234567", "+998901234567",
    with arbitrary spaces/dashes/parentheses. Raises InvalidPhoneNumber if the
    result isn't a valid Uzbek number.
    """
    digits = re.sub(r"\D", "", raw or "")

    if len(digits) == 9:
        candidate = f"+998{digits}"
    elif len(digits) == 12 and digits.startswith("998"):
        candidate = f"+{digits}"
    else:
        candidate = f"+{digits}" if digits else ""

    if not UZ_PHONE_RE.match(candidate):
        raise InvalidPhoneNumber(
            "Enter a valid Uzbekistan phone number, e.g. +998901234567."
        )

    return candidate
