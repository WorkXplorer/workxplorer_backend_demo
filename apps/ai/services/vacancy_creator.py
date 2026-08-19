"""
AI-powered vacancy creation service.

Fetches vacancy data from external URLs or processes raw text,
uses AI to extract structured vacancy information, matches skills and
domains from the database, and creates the Vacancy with all relations.
"""

import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.db import transaction
from django_rq import enqueue

from apps.domain.models import Domain
from apps.matching.services.embedding_tasks import generate_vacancy_embedding_task
from apps.skills.models import Skill
from apps.vacancies.models import Vacancy, VacancySkill
from utils.prompt_sanitizer import sanitize_prompt_value

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a vacancy data extraction assistant for the WorkXplorer job platform \
(Uzbekistan). Extract structured vacancy information from the provided text.

RULES:
1. Preserve the original language of the text. If the source is in Russian, \
output everything in Russian. If English, output in English. If Uzbek, output in Uzbek.
2. For experience ranges (e.g. "1-3 years", "2-5 лет", "3-5 yil"), calculate the \
average and return a single integer (e.g. 2, 4, 3). If no experience is mentioned, use 0.
3. If any field information is missing from the text, use empty string for text fields, \
null for nullable fields, or sensible defaults. Do NOT invent or hallucinate values.
4. Map employment types appropriately: FULL_TIME (full-time/полная), PART_TIME \
(part-time/частичная), CONTRACT (contract/контракт), INTERNSHIP (internship/стажировка).
5. Map employment formats: ON_SITE (office/на месте), REMOTE (remote/удаленно), \
HYBRID (hybrid/гибрид).
6. For salary, extract min/max/currency if mentioned. Currency defaults to UZS if not \
specified.
7. MATCH SKILLS: Below you will receive a list of AVAILABLE SKILLS with IDs. Your task \
is to identify which skills from that list are required for this vacancy. Return their \
IDs in the "matching_skill_ids" array. Only include skills that are explicitly mentioned \
or clearly implied by the vacancy requirements. If no skills match, return an empty array.
8. MATCH DOMAIN: Below you will receive a list of AVAILABLE DOMAINS. Pick the single \
most relevant domain name for this vacancy (exactly as written in the list). \
If none fit, return null. Do NOT pick a domain unless it clearly matches.

9. For location coordinates, extract latitude and longitude if explicitly provided \
in the vacancy text. Otherwise return null for both.

Respond with a single JSON object:
{
  "title": "...",
  "requirements": "...",
  "responsibilities": "...",
  "about_us": "...",
  "additional_info": "...",
  "experience": 0,
  "employment_type": "FULL_TIME",
  "employment_format": "ON_SITE",
  "salary_min": null,
  "salary_max": null,
  "salary_currency": "UZS",
  "location": "...",
  "latitude": null,
  "longitude": null,
  "contact_email": "...",
  "contact_phone": "...",
  "number_of_positions": 1,
  "expire": 30,
  "matching_skill_ids": [],
  "domain_name": null
}

Output raw JSON only — no markdown, no explanations outside the JSON."""


# ---------------------------------------------------------------------------
# URL fetching
# ---------------------------------------------------------------------------

def fetch_url_content(url: str) -> str:
    """
    Fetch a URL and extract readable text content.

    Uses a browser-like User-Agent to avoid blocking and strips
    non-content HTML elements (script, style, nav, footer, header).
    """
    # SSRF protection: only http/https and only public IPs
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed.")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL is missing a hostname.")

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname: {hostname}") from exc

    for _, _, _, _, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ValueError(
                f"URL resolves to a non-public IP address ({sockaddr[0]})."
            )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ---------------------------------------------------------------------------
# Compact data helpers (token-efficient)
# ---------------------------------------------------------------------------

def _build_skills_block() -> str:
    """
    Return a compact string of all active skills.

    Format:
      1|Python
      2|JavaScript
      ...
    ~800 lines, ~10 KB — well within token limits.
    """
    skills = (
        Skill.objects.filter(is_active=True)
        .only("id", "name")
        .order_by("name")
    )
    lines = [f"{s.id}|{s.name}" for s in skills]
    return "AVAILABLE SKILLS (id|name):\n" + "\n".join(lines)


def _build_domains_block() -> str:
    """
    Return a compact string of all domains.

    Format:
      - Information Technology
      - Healthcare
      ...
    ~50 lines, very small.
    """
    domains = Domain.objects.only("name").order_by("name")
    lines = [f"- {d.name}" for d in domains]
    return "AVAILABLE DOMAINS:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# AI communication
# ---------------------------------------------------------------------------

def _build_user_message(source_text: str) -> str:
    """Build the user message with source text + compressed skills/domains."""
    parts = [
        "VACANCY SOURCE TEXT:",
        sanitize_prompt_value(source_text, max_length=50000),
        "",
        _build_skills_block(),
        "",
        _build_domains_block(),
    ]
    return "\n".join(parts)


def _build_messages(source_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(source_text)},
    ]


def _parse_ai_response(ai_client, raw_response: dict[str, Any]) -> dict[str, Any]:
    content = raw_response["choices"][0]["message"]["content"]
    try:
        return ai_client.parse_json_response(content)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AI response: %s", str(exc))
        raise RuntimeError("AI returned invalid JSON.") from exc


def extract_vacancy_data(ai_client, source_text: str) -> dict[str, Any]:
    """
    Send source text to AI and get structured vacancy data back.
    """
    messages = _build_messages(source_text)

    logger.info(
        "Sending vacancy extraction request to AI (%d chars in source)",
        len(source_text),
    )

    raw_response = ai_client.cached_completion(
        messages, "vacancy_extract", source_text, json_mode=True
    )
    return _parse_ai_response(ai_client, raw_response)


# ---------------------------------------------------------------------------
# Sanitizers
# ---------------------------------------------------------------------------

def _sanitize_experience(value: Any) -> int:
    try:
        val = int(float(str(value)))
        return max(val, 0)
    except (ValueError, TypeError):
        return 0


def _sanitize_int(value: Any, default: int = 1) -> int:
    try:
        val = int(float(str(value)))
        return max(val, 0)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Vacancy creation with skill + domain linking
# ---------------------------------------------------------------------------

def _resolve_domain(extracted: dict[str, Any]):
    """
    Look up a Domain by name from the AI output.

    Tries exact match first, then partial match if nothing found.
    Returns the Domain instance or None.
    """
    domain_name = extracted.get("domain_name")
    if not domain_name:
        return None

    cleaned = domain_name.strip()

    # Exact match (case-insensitive)
    domain = Domain.objects.filter(name__iexact=cleaned).first()
    if domain:
        return domain

    # Partial match fallback — find domain where the cleaned name
    # is contained within or contains the stored name
    domain = (
        Domain.objects.filter(name__icontains=cleaned)
        .order_by("name")
        .first()
    )
    if not domain:
        # Also try the reverse: stored name contained in AI output
        for d in Domain.objects.only("name").order_by("name"):
            if cleaned.lower() in d.name.lower() or d.name.lower() in cleaned.lower():
                domain = d
                break

    if domain:
        logger.info(
            "Domain fuzzy-matched '%s' -> '%s' (id=%s)",
            cleaned, domain.name, domain.id,
        )
    else:
        logger.warning("Domain not found (no match): '%s'", cleaned)

    return domain


def _resolve_skill_ids(extracted: dict[str, Any]) -> list[Skill]:
    raw_ids = extracted.get("matching_skill_ids", [])
    if not raw_ids:
        return []

    try:
        candidate_ids = list({int(i) for i in raw_ids if i is not None})
    except (ValueError, TypeError):
        logger.warning("Invalid skill IDs in AI output: %s", raw_ids)
        return []

    return list(Skill.objects.filter(id__in=candidate_ids, is_active=True))


def _create_vacancy_skills(vacancy: Vacancy, skills: list[Skill]) -> None:
    if not skills:
        return

    records = [
        VacancySkill(
            vacancy=vacancy,
            skill=skill,
            is_required=True,
            minimum_years=0,
            proficiency_level="UNDEFINED",
        )
        for skill in skills
    ]

    VacancySkill.objects.bulk_create(records, ignore_conflicts=True)
    logger.info("Linked %d skills to vacancy #%s", len(records), vacancy.id)


@transaction.atomic
def create_vacancy_from_data(
    extracted: dict[str, Any],
    recruiter,
    company,
) -> Vacancy:
    """
    Create a Vacancy object from AI-extracted structured data,
    including skill and domain linking.

    Args:
        extracted: Dict with vacancy fields from AI extraction.
        recruiter: The authenticated Recruiter instance.
        company: The recruiter's Company instance.

    Returns:
        The created Vacancy instance.
    """
    domain = _resolve_domain(extracted)

    vacancy = Vacancy.objects.create(
        created_by=recruiter,
        company=company,
        domain=domain,
        title=extracted.get("title", ""),
        requirements=extracted.get("requirements", ""),
        responsibilities=extracted.get("responsibilities", ""),
        about_us=extracted.get("about_us", ""),
        additional_info=extracted.get("additional_info", ""),
        experience=_sanitize_experience(extracted.get("experience", 0)),
        employment_type=extracted.get("employment_type", "FULL_TIME"),
        employment_format=extracted.get("employment_format", "ON_SITE"),
        salary_min=extracted.get("salary_min"),
        salary_max=extracted.get("salary_max"),
        salary_currency=extracted.get("salary_currency", "UZS"),
        location=extracted.get("location", ""),
        latitude=extracted.get("latitude"),
        longitude=extracted.get("longitude"),
        contact_email=extracted.get("contact_email", ""),
        contact_phone=extracted.get("contact_phone", ""),
        number_of_positions=_sanitize_int(extracted.get("number_of_positions", 1)),
        expire=_sanitize_int(extracted.get("expire", 30), 30),
        minimum_ai_score=_sanitize_int(extracted.get("minimum_ai_score", 40), 40),
    )

    skills = _resolve_skill_ids(extracted)
    _create_vacancy_skills(vacancy, skills)

    transaction.on_commit(
        lambda: enqueue(generate_vacancy_embedding_task, vacancy.id)
    )

    logger.info(
        "AI-created vacancy #%s: title=%s, company=%s, skills=%d, domain=%s",
        vacancy.id,
        vacancy.title,
        company.name,
        len(skills),
        domain.name if domain else "none",
    )

    return vacancy


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def create_vacancy_from_text(
    ai_client, source_text: str, recruiter, company
) -> Vacancy:
    """
    Full pipeline: AI extracts structured data from text, matches skills
    and domains, then creates the vacancy with all relations.

    Args:
        ai_client: GroqClient instance.
        source_text: Raw text describing the vacancy (from URL fetch or direct input).
        recruiter: The authenticated Recruiter instance.
        company: The recruiter's Company instance.

    Returns:
        The created Vacancy instance.
    """
    extracted = extract_vacancy_data(ai_client, source_text)
    return create_vacancy_from_data(extracted, recruiter, company)
