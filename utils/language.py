"""
Centralized language utilities for the WorkXplorer platform.

Provides a single source of truth for extracting the user's preferred language
from the request. All views, serializers, and middleware should use these
utilities instead of manually parsing the Accept-Language header.

Django's LocaleMiddleware (already registered) handles calling
`translation.activate()` based on Accept-Language, so
`translation.get_language()` returns the correct language within any
request lifecycle. This module wraps that with validation against the
platform's supported languages.

Supported languages: uz, ru, en
Default language: uz
"""

from django.utils.translation import get_language

SUPPORTED_LANGUAGES = ("uz", "ru", "en")
DEFAULT_LANGUAGE = "uz"


def get_request_language() -> str:
    """
    Return the active language code for the current request.

    Uses Django's translation framework (activated by LocaleMiddleware
    from the Accept-Language header) and validates against the platform's
    supported languages.

    Returns:
        str: One of 'uz', 'ru', 'en'. Defaults to 'uz'.
    """
    lang = get_language()
    if lang:
        # Handle codes like 'en-us' -> 'en'
        lang = lang.split("-")[0].lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    return lang
