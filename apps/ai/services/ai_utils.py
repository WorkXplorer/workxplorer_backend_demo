import hashlib
import json
import re
from typing import Any


def build_cache_key(prefix: str, *params: str) -> str:
    fingerprint = hashlib.sha256("|".join(params).encode("utf-8")).hexdigest()
    return f"{prefix}:{fingerprint}"


def strip_code_fence(raw_text: str) -> str:
    """Remove markdown code fences from a response string."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_response(raw_text: str) -> dict[str, Any]:
    """Parse a JSON response, stripping code fences if needed."""
    cleaned = strip_code_fence(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group(0))
        raise
