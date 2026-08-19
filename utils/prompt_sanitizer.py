import re
import unicodedata
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structural token patterns — syntactic delimiters that LLM APIs interpret as
# role boundaries. These are reliably detectable regardless of phrasing.
# ---------------------------------------------------------------------------
_STRUCTURAL_DELIMITER_PATTERNS = [
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<\|system\|>",
    r"<\|user\|>",
    r"<\|assistant\|>",
    r"<\|endoftext\|>",
    r"<\|end\|>",
    r"\[INST\]\s*",
    r"\s*\[/INST\]",
    r"<<SYS>>\s*",
    r"\s*<</SYS>>",
    r"<function_calls>",
    r"</function_calls>",
    r"<function_call>",
    r"</function_call>",
    r"<tool_calls>",
    r"</tool_calls>",
    r"<tool_call>",
    r"</tool_call>",
    r"<system>",
    r"</system>",
    r"<user>",
    r"</user>",
    r"<assistant>",
    r"</assistant>",
]
_COMPILED_DELIMITERS = [re.compile(p) for p in _STRUCTURAL_DELIMITER_PATTERNS]

# ---------------------------------------------------------------------------
# Instruction-override phrase patterns — natural-language injection attempts.
# Inputs matching these are rejected rather than sanitised because detecting
# them after character mangling is unreliable; it's safer to refuse the
# entire payload at the application layer.
# ---------------------------------------------------------------------------
_INSTRUCTION_OVERRIDE_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?|context|directives)",
    r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|context)",
    r"override\s+(system\s+)?(instructions|prompt|directives)",
    r"you\s+are\s+(now\s+)?(a\s+)?(free|unbound|released|ungoverned|independent)\s+",
    r"new\s+(instructions|prompt|task|role)(\s*[:\-])",
    r"act\s+as\s+(if|though)\s+you\s+(are|were)",
    r"do\s+not\s+follow\s+(the\s+)?(above|system|previous)",
    r"output\s+the\s+(system\s+)?(prompt|instructions|directives)",
    r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions)",
    r"print\s+(your\s+)?(system\s+)?(prompt|directives)",
    r"repeat\s+(all\s+)?(the\s+)?(above|previous|how\s+to)",
    r"disregard\s+(all\s+)?(prior|previous)\s+(instructions|directives)",
    r"never\s+(mind|respond|follow)",
    r"forget\s+the\s+instructions",
]
_INSTRUCTION_RE = re.compile(
    "|".join(_INSTRUCTION_OVERRIDE_PATTERNS),
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Homoglyph map for pre-detection normalisation — Cyrillic lookalikes,
# Roman-numeral lookalikes, and common confusables that bypass simple
# ASCII keyword matching.
# ---------------------------------------------------------------------------
_HOMOGLYPH_MAP = {
    ord('A'): 'A', ord('B'): 'B', ord('E'): 'E', ord('K'): 'K',
    ord('M'): 'M', ord('H'): 'H', ord('O'): 'O', ord('P'): 'P',
    ord('C'): 'C', ord('T'): 'T', ord('Y'): 'Y', ord('X'): 'X',
    ord('a'): 'a', ord('e'): 'e', ord('o'): 'o', ord('p'): 'p',
    ord('c'): 'c', ord('y'): 'y', ord('x'): 'x',
    'Ⅰ': 'I', 'Ⅱ': 'II', 'Ⅲ': 'III', 'Ⅳ': 'IV', 'Ⅴ': 'V',
    'Ⅵ': 'VI', 'Ⅶ': 'VII', 'Ⅷ': 'VIII', 'Ⅸ': 'IX', 'Ⅹ': 'X',
}


def _normalise_homoglyphs(text: str) -> str:
    """Replace Unicode homoglyphs with their ASCII equivalents."""
    return text.translate(_HOMOGLYPH_MAP)


def detect_prompt_injection(text: str) -> Optional[str]:
    """
    Check whether *text* contains a likely prompt-injection pattern.

    NFKC-normalises then homoglyph-normalises the input before matching
    so that lookalike characters (Cyrillic, Greek, fullwidth, mathematical
    script, Roman numerals, etc.) do not bypass detection.

    Args:
        text: The user-supplied string to inspect.

    Returns:
        The matched pattern string if an injection was found, or ``None``.
    """
    normalised = unicodedata.normalize("NFKC", text)
    normalised = _normalise_homoglyphs(normalised)
    match = _INSTRUCTION_RE.search(normalised)
    if match:
        return match.group()
    return None


def sanitize_prompt_value(value: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize a user-controlled string for safe inclusion in an AI prompt.

    Performs:
    1. NFKC Unicode normalization
    2. Control-character removal (except newlines/tabs)
    3. Unicode-format-character removal (Cf category)
    4. Structural delimiter stripping (ChatML, Llama, OpenAI XML tags)
    5. Consecutive newline collapsing
    6. Optional truncation

    This function does **not** attempt to detect phrase-level injection
    patterns — that responsibility belongs to the caller via
    :func:`detect_prompt_injection`.

    Args:
        value: The string to sanitize.
        max_length: Hard truncation length, or None for no truncation.

    Returns:
        The sanitized string. If value is None or empty, returns empty string.
        Non-string inputs are logged as a warning and coerced via str().
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        logger.warning(
            "sanitize_prompt_value called with non-string type %s",
            type(value).__name__,
        )
        value = str(value)

    value = unicodedata.normalize("NFKC", value)

    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", value)

    value = "".join(c for c in value if unicodedata.category(c) != "Cf")

    for pattern in _COMPILED_DELIMITERS:
        value = pattern.sub("", value)

    value = re.sub(r"\n{3,}", "\n\n", value)

    value = value.strip()

    if max_length is not None and len(value) > max_length:
        value = value[:max_length].rstrip()

    return value


def sanitize_prompt_list(values: list, max_length: Optional[int] = None) -> list:
    return [sanitize_prompt_value(v, max_length) for v in values]
