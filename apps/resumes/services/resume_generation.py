"""
Resume generation service using an AI provider.

Provides intelligent resume parsing and generation with semantic skill mapping,
domain identification, and multi-language support.
"""

import datetime
import html
import json
import logging
import re
import subprocess
import textwrap
import zipfile
from pathlib import Path
from typing import Any, Optional

import bleach
from defusedxml import ElementTree

from django.db.models import Q

from apps.ai.services.ai_provider_client import AIProviderClient
from apps.resumes.services.skill_resolution import (
    MIN_TOKEN_SIMILARITY,
    SkillResolver,
    _similarity,
)
from utils.prompt_sanitizer import sanitize_prompt_value, detect_prompt_injection

logger = logging.getLogger(__name__)

# AI Response Cache Configuration.
# The cache key is built from the *input* (source text and instructions) only —
# the prompt itself is not part of it — so a cached response outlives any change
# to what the prompt asks for. Bump this suffix whenever the requested output
# shape changes, or the same resume keeps returning the answer to the old
# question for as long as AI_RESPONSE_CACHE_TIMEOUT (24h by default).
AI_CACHE_KEY_PREFIX = "ai_resume_gen_v7_mentions"

ai_client = AIProviderClient()

# A resume carries a shortlist, not an inventory. The serializer accepts 25
# (MAX_RESUME_SKILLS); generation stops short of that so a candidate keeps room
# to add their own afterwards.
MAX_GENERATED_SKILLS = 20

_WHITESPACE_RE = re.compile(r'\s+')


class DomainMatcher:
    """
    Matches domain names to database domains across all language variants.
    
    Uses a 3-tier fallback strategy:
    1. Exact match (case-insensitive) on name and translated fields
    2. Partial match (icontains) on name and translated fields
    3. Reverse partial match — checks if AI output name is contained within
       stored domain name or vice versa (Python fallback loop)
    """
    
    @staticmethod
    def find_matching_domain(domain_name: Optional[str]) -> Optional[dict]:
        """
        Find a domain by name across all language variants.
        
        Args:
            domain_name: Domain name to match
            
        Returns:
            Matched domain dict or None
        """
        if not domain_name:
            return None
        
        from apps.domain.models import Domain
        
        cleaned = domain_name.strip()
        
        # 1. Exact match (case-insensitive) on all translated name fields
        domain = Domain.objects.filter(
            Q(name__iexact=cleaned)
            | Q(name_en__iexact=cleaned)
            | Q(name_ru__iexact=cleaned)
            | Q(name_uz__iexact=cleaned)
        ).first()
        
        if domain:
            return {
                'id': domain.id,
                'name': domain.name,
            }
        
        # 2. Partial match — stored name contains the AI-provided string
        domain = Domain.objects.filter(
            Q(name__icontains=cleaned)
            | Q(name_en__icontains=cleaned)
            | Q(name_ru__icontains=cleaned)
            | Q(name_uz__icontains=cleaned)
        ).order_by("name").first()
        
        if domain:
            logger.info(
                "Domain icontains-matched '%s' -> '%s' (id=%s)",
                cleaned, domain.name, domain.id,
            )
            return {
                'id': domain.id,
                'name': domain.name,
            }
        
        # 3. Reverse partial match — Python fallback
        for d in Domain.objects.only("name", "name_en", "name_ru", "name_uz").order_by("name"):
            stored_names = [n for n in [d.name, d.name_en, d.name_ru, d.name_uz] if n]
            for stored in stored_names:
                if cleaned.lower() in stored.lower() or stored.lower() in cleaned.lower():
                    logger.info(
                        "Domain reverse-matched '%s' -> '%s' (id=%s)",
                        cleaned, d.name, d.id,
                    )
                    return {
                        'id': d.id,
                        'name': d.name,
                    }
        
        logger.warning("Domain not found (no match): '%s'", cleaned)
        return None


class LanguageMatcher:
    """
    Matches a language named by the model to a row in the language table.

    Names are stored in whatever language the admin typed ("Русский", "O'zbek"),
    so matching on the name alone fails half the time. The model is asked for an
    ISO 639-1 code as well, which is the one identifier both sides agree on.
    """

    # Spellings a resume actually uses for the three languages of this market.
    NAME_ALIASES = {
        'en': ('english', 'английский', 'английский язык', 'ingliz', 'ingliz tili', 'inglizcha'),
        'ru': ('russian', 'русский', 'русский язык', 'rus', 'rus tili', 'ruscha'),
        'uz': ('uzbek', 'узбекский', 'узбекский язык', "o'zbek", "o'zbek tili", 'ozbek', 'uzbekcha'),
    }

    @staticmethod
    def find_matching_language(
        language_name: Optional[str], language_code: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Find a language by ISO code or by any spelling of its name.

        Args:
            language_name: Language name as written by the model
            language_code: ISO 639-1 code, when the model supplied one

        Returns:
            Matched language dict or None
        """
        from apps.languages.models import Language

        code = (language_code or '').strip().lower()[:2]
        name = (language_name or '').strip().lower()

        if not code and name:
            for alias_code, aliases in LanguageMatcher.NAME_ALIASES.items():
                if name in aliases:
                    code = alias_code
                    break

        query = Q()
        if code:
            query |= Q(code__iexact=code)
        if name:
            query |= Q(name__iexact=name) | Q(code__iexact=name)

        if not query:
            return None

        language = Language.objects.filter(query).first()
        if not language:
            return None

        return {
            'id': language.id,
            'name': language.name,
            'code': language.code,
        }


def get_system_prompt(input_language: str = "en", has_github_context: bool = False, has_social_url: bool = False) -> str:
    """
    Build the system prompt for the reading stage.

    The model is asked for one thing: report what the source says. It never
    sees the platform's skill vocabulary and is never asked to choose a
    canonical name from it — that job belongs to
    :mod:`apps.resumes.services.skill_resolution`, which can compare English to
    English instead of Russian to English.

    Splitting those jobs is what makes the instructions consistent. While the
    model had to satisfy both at once, every rule that improved accuracy
    ("copy names from the list", "quote the source", "stay in the candidate's
    field") cost recall, and the output collapsed to a couple of skills.

    Args:
        input_language: Detected input language ('en', 'ru', 'uz')
        has_github_context: Whether GitHub profile data is provided
        has_social_url: Whether a portfolio/social URL is provided

    Returns:
        System prompt string
    """
    language_instructions = {
        "en": "Write prose fields in English.",
        "ru": "Пишите текстовые поля на русском языке.",
        "uz": "Matnli maydonlarni o'zbek tilida yozing.",
    }

    lang_instruction = language_instructions.get(input_language, language_instructions["en"])

    context_instructions = ""

    if has_github_context:
        context_instructions += (
            "\nGitHub Context provided in the user prompt. Treat repository languages "
            "and topics as source text: they are quotable evidence for technical "
            "skills. Mention significant stars/forks in the description. "
            "Do NOT invent employers or job titles from GitHub data."
        )

    if has_social_url:
        context_instructions += (
            "\nPortfolio link provided. Store it in candidate_profile.portfolio only. "
            "Do not attempt to browse or analyse the URL contents."
        )

    return textwrap.dedent(
        f"""
        You are a WorkXplorer resume parser. Convert the source into a single JSON object.
        {lang_instruction}
        {context_instructions}

        Output rules:
        - Raw JSON only, no markdown, no explanations
        - Never invent employers, degrees, dates, salaries or links that are not in the source
        - Plain text everywhere: no HTML, no markdown, no HTML entities. Write "&", not "&amp;"

        --- skill_mentions: the part that matters most ---
        Sweep the entire source and report every skill it shows. For each one:
        - "quote": the exact words from the source, copied character-for-character in
          the source's own language. Never translate, paraphrase or tidy a quote —
          it is checked against the source and a rewritten quote loses the skill.
        - "skill": the standard English name of that skill, spelled the way the
          industry spells it: "System Analysis", "BPMN", "Sequence Diagram",
          "PostgreSQL", "Stakeholder Management".
        - "minimum_years" and "proficiency_level": from the experience the skill
          appears in; null and "UNDEFINED" when the source gives no basis.

        - Be specific. When the source names a concrete technology, standard or
          tool, that exact thing is the skill: "Умею BPMN, Sequence diagram" gives
          BPMN and Sequence Diagram — two mentions, never one merged entry, never a
          broader category standing in for what was named.
        - Be exhaustive. A resume describing real work usually shows 8-15 skills:
          technologies, methodologies, standards, platforms, domain knowledge and
          professional competencies all count, not only named software. One
          sentence can support several mentions — quote it once per skill.
        - Be honest. A skill needs words in the source behind it. Never add a skill
          because an employer, a domain or a profession makes it likely: a resume that
          claims something the candidate did not say is worse than a short one.
        - The one thing a stated role does prove is the work it names. "Системный
          аналитик" is a mention of System Analysis, "Backend-разработчик" of Backend
          Development — same words, quoted from the title itself. It says nothing about
          the other skills someone in that role often has; those still need their own
          words in the source.

        --- Everything else ---
        - Ignore education entries entirely (no field for them yet)
        - Dates: YYYY-MM-DD (exact) | YYYY-MM-01 (month only) | YYYY-01-01 (year only) | null end_date if ongoing
        - Total experience across experiences_data must not exceed what the source states
        - Every experience needs a non-empty "description": 2-4 sentences on responsibilities, achievements and technologies
        - For country/city, infer from the company when it is knowable ("Beeline Uzbekistan" → Uzbekistan, Tashkent)
        - work_status enum: ACTIVELY_LOOKING|OPEN_TO_OPPORTUNITIES|NOT_LOOKING|PART_TIME_CONSIDERING|EMPLOYED|SELF_EMPLOYED|FREELANCER|INTERNSHIP|STUDENT|UNEMPLOYED
        - proficiency_level enum: UNDEFINED|BEGINNER|INTERMEDIATE|ADVANCED|EXPERT
        - language levels: A1|A2|B1|B2|C1|C2
        - languages: include one entry per language the source actually names, with its
          ISO 639-1 code ("en", "ru", "uz"). Take the level from what the source says —
          an explicit CEFR level; "свободный"/"fluent"/"advanced" → C1; "родной"/"native" → C2;
          "разговорный"/"conversational"/"intermediate" → B1; "базовый"/"basic" → A2;
          IELTS 7+/TOEFL 94+ → C1, IELTS 5.5-6.5 → B2. When the source names a language
          with no hint of level at all, use B1 — the candidate can correct it on review.
          Never list a language the source does not mention.
        - description: the candidate's professional summary, 3-5 sentences, written to be
          read by a recruiter in ten seconds. Open with what they are and how long they
          have done it ("Системный аналитик с 3 годами опыта в финтехе"). Then the
          substance: the products or domains they worked on, the scale or results where
          the source gives them, the tools and methods they actually use. Close with the
          direction they are heading if the source shows it. Draw every claim from the
          source — no invented employers, numbers or seniority — and drop the filler
          adjectives ("ответственный", "целеустремлённый", "hardworking"): a recruiter
          discounts them, and they crowd out the facts that do the work. Write it in the
          source's language.
        - position: the job title alone ("Founder & CEO"), without the company
        - Pick domain_name from the AVAILABLE DOMAINS list in the user prompt. Choose the single
          most relevant one, copied exactly. If none fit, return null.
        - Detect the input language and set detected_language

        JSON shape:
        {{
          "source_type": "file|prompt|combined",
          "detected_language": "en|ru|uz",
          "candidate_profile": {{
            "full_name": null, "email": null, "phone": null,
            "address": null, "linkedin": null, "github": null, "portfolio": null
          }},
          "skill_mentions": [
            {{ "quote": "verbatim words from the source", "skill": "Standard English Name",
               "minimum_years": 0, "proficiency_level": "enum" }}
          ],
          "resume": {{
            "description": "", "position": "",
            "domain_name": null, "work_status": "enum",
            "current_company_name": null, "current_position": null,
            "employment_start_date": null, "current_salary": null,
            "salary_currency": "USD|UZS|EUR|null", "salary_hide": true,
            "experiences_data": [
              {{ "company": "", "role": "", "country": "", "city": "",
                 "start_date": "", "end_date": null, "description": "" }}
            ],
            "certificates_data": [
              {{ "name": null, "issuing_organization": null, "issue_date": null,
                 "expiration_date": null, "credential_id": null, "credential_url": null }}
            ],
            "language_certificates_data": [
              {{ "language_name": "English", "language_code": "en", "level": "A1|A2|B1|B2|C1|C2" }}
            ]
          }}
        }}
        """
    ).strip()


def _build_domains_block() -> str:
    """
    Build a compact string of all available domains for the AI prompt.
    
    Format:
      - Information Technology
      - Healthcare
      ...
    """
    from apps.domain.models import Domain

    domains = Domain.objects.only("name").order_by("name")
    lines = [f"- {d.name}" for d in domains]

    if not lines:
        # Without this the model invents a plausible-sounding domain ("Fintech")
        # that resolves to nothing, and the null domain_id reads like a matching
        # bug rather than an unconfigured table.
        return (
            "AVAILABLE DOMAINS: none are configured on this platform.\n"
            "Set domain_name to null — do not invent one."
        )

    return "AVAILABLE DOMAINS:\n" + "\n".join(lines)




def build_user_prompt(source_type: str, payload: str, additional_instructions: str = "") -> str:
    """
    Build user prompt for AI API.
    
    Args:
        source_type: Type of source (file, prompt, combined)
        payload: The content to process
        additional_instructions: Additional instructions to append
        
    Returns:
        User prompt string
        
    Raises:
        ValueError: If payload contains prompt-injection patterns
    """
    injection_match = detect_prompt_injection(payload)
    if injection_match:
        logger.warning("Prompt injection detected in payload: matched '%s'", injection_match)
        raise ValueError("Source content rejected: contains invalid instructions.")

    prompt = textwrap.dedent(
        f"""
        Source type: {sanitize_prompt_value(source_type)}

        Convert the following source into the WorkXplorer JSON structure exactly as instructed.

        Source content:
        {sanitize_prompt_value(payload, max_length=20000)}
        """
    ).strip()
    
    prompt += f"\n\n{_build_domains_block()}"

    prompt += textwrap.dedent(
        """

        Report a skill only when the source shows it. A named tool, standard or
        technology is a mention on its own terms; a duty phrased as a sentence
        ("писал документацию") is a mention of the skill it demonstrates. Skills
        belonging to a profession the candidate does not work in — clinical
        procedures on an engineer's resume — are not mentions, however common the
        words are.
        """
    )

    if additional_instructions:
        sanitized_ai = sanitize_prompt_value(additional_instructions, max_length=2000)
        injection_match = detect_prompt_injection(sanitized_ai)
        if injection_match:
            logger.warning(
                "Prompt injection detected in additional_instructions: matched '%s'",
                injection_match,
            )
            raise ValueError("Additional instructions rejected: contains invalid instructions.")
        prompt += f"\n\nAdditional instructions:\n{sanitized_ai}"
    
    return prompt


def detect_language(text: str) -> str:
    """
    Detect the language of the input text.
    
    Args:
        text: Text to analyze
        
    Returns:
        Language code ('en', 'ru', 'uz')
    """
    if not text:
        return "en"
    
    text_lower = text.lower()
    
    # Count language-specific characters
    ru_chars = sum(1 for c in text_lower if '\u0400' <= c <= '\u04ff')
    uz_chars = sum(1 for c in text_lower if c in 'oʻgʻʻ')
    
    # Common Russian words
    ru_words = ['и', 'в', 'не', 'на', 'я', 'что', 'тот', 'быть', 'с', 'а', 'по', 'это', 'она', 'к', 'но', 'мы', 'как', 'из', 'за', 'от']
    ru_count = sum(1 for word in ru_words if f' {word} ' in f' {text_lower} ')
    
    # Common Uzbek words
    uz_words = ['va', 'bir', 'bu', 'uchun', 'ham', 'bilan', 'dan', 'ga', 'ki', 'deb', 'edi', 'kabi', 'shu', 'har']
    uz_count = sum(1 for word in uz_words if f' {word} ' in f' {text_lower} ')
    
    if ru_chars > 10 or ru_count >= 3:
        return "ru"
    elif uz_chars > 2 or uz_count >= 3:
        return "uz"
    else:
        return "en"


def extract_docx_text(file_content: bytes) -> str:
    """
    Extract text from DOCX file content.
    
    Args:
        file_content: Binary content of DOCX file
        
    Returns:
        Extracted text
    """
    import io
    
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as archive:
            info = archive.getinfo("word/document.xml")
            MAX_XML_SIZE = 50 * 1024 * 1024  # 50MB decompressed limit
            if info.file_size > MAX_XML_SIZE:
                logger.error("DOCX XML too large: %d bytes (limit %d)", info.file_size, MAX_XML_SIZE)
                return ""
            document_xml = archive.read("word/document.xml")
        
        root = ElementTree.fromstring(document_xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        
        for paragraph in root.findall(".//w:p", namespace):
            chunks = []
            for node in paragraph.findall(".//w:t", namespace):
                if node.text:
                    chunks.append(node.text)
            text = "".join(chunks).strip()
            if text:
                paragraphs.append(text)
        
        return "\n".join(paragraphs)
    except Exception as e:
        logger.error(f"Error extracting DOCX text: {e}")
        return ""


def extract_pdf_text(file_content: bytes) -> str:
    """
    Extract text from PDF file content using pdftotext.
    
    Args:
        file_content: Binary content of PDF file
        
    Returns:
        Extracted text
    """
    import tempfile
    import shutil
    
    pdftotext_path = shutil.which("pdftotext")
    if not pdftotext_path:
        logger.warning("pdftotext not found. PDF extraction may not work properly.")
        # Try using pypdf as fallback
        try:
            from pypdf import PdfReader
            import io
            
            reader = PdfReader(io.BytesIO(file_content))
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts).strip()
        except ImportError:
            logger.error("pypdf not available for PDF extraction fallback")
            return ""
    
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            tmp_file.write(file_content)
            tmp_path = tmp_file.name
        
        result = subprocess.run(
            [pdftotext_path, tmp_path, "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"pdftotext error: {result.stderr}")
            return ""
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        return ""
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def extract_file_text(file_content: bytes, file_extension: str) -> str:
    """
    Extract text from file content based on extension.
    
    Args:
        file_content: Binary file content
        file_extension: File extension (e.g., '.pdf', '.docx')
        
    Returns:
        Extracted text
    """
    suffix = file_extension.lower()
    
    if suffix == ".docx":
        return extract_docx_text(file_content)
    elif suffix == ".pdf":
        return extract_pdf_text(file_content)
    else:
        raise ValueError(f"Unsupported file format: {file_extension}")


def generate_resume(
    source_type: str,
    content: str,
    additional_instructions: str = "",
    has_github_context: bool = False,
    has_social_url: bool = False,
) -> dict[str, Any]:
    detected_language = detect_language(content)

    response = ai_client.cached_completion(
        [
            {"role": "system", "content": get_system_prompt(detected_language, has_github_context, has_social_url)},
            {"role": "user", "content": build_user_prompt(source_type, content, additional_instructions)},
        ],
        AI_CACHE_KEY_PREFIX,
        source_type,
        content,
        additional_instructions,
        str(has_github_context),
        str(has_social_url),
        json_mode=True,
    )

    raw_content = response["choices"][0]["message"]["content"]
    cleaned_content = ai_client.strip_code_fence(raw_content)

    try:
        result = json.loads(cleaned_content)
        result["detected_language"] = detected_language
        _validate_ai_output(result)
        return result
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse AI response (len=%d, first_200=%s ...)",
            len(raw_content),
            raw_content[:200].replace("\n", "\\n"),
        )
        raise RuntimeError("AI returned non-JSON response.") from exc


def _validate_ai_output(result: dict) -> None:
    """
    Validate and normalise an AI-generated resume response in-place.

    Checks required keys, enum constraints, numeric ranges, and strips
    obvious XSS payloads from free-text fields.

    Args:
        result: The parsed AI response dict.  Modified in-place.

    Raises:
        ValueError: If the response is structurally invalid (missing
                     required keys or wrong types).
    """
    for key in ('source_type', 'candidate_profile', 'resume'):
        if key not in result:
            raise ValueError(f"AI response missing required key: '{key}'")

    resume = result['resume']
    if not isinstance(resume, dict):
        raise ValueError("AI response 'resume' is not a dict")

    # --- Enums -----------------------------------------------------------------
    valid_work_status = {
        'ACTIVELY_LOOKING', 'OPEN_TO_OPPORTUNITIES', 'NOT_LOOKING',
        'PART_TIME_CONSIDERING', 'EMPLOYED', 'SELF_EMPLOYED',
        'FREELANCER', 'INTERNSHIP', 'STUDENT', 'UNEMPLOYED',
    }
    ws = resume.get('work_status')
    if ws and ws not in valid_work_status:
        resume['work_status'] = 'ACTIVELY_LOOKING'

    valid_proficiency = {'UNDEFINED', 'BEGINNER', 'INTERMEDIATE', 'ADVANCED', 'EXPERT'}
    mentions = result.get('skill_mentions')
    if not isinstance(mentions, list):
        result['skill_mentions'] = mentions = []

    for mention in mentions:
        if not isinstance(mention, dict):
            continue
        level = mention.get('proficiency_level')
        if level and level not in valid_proficiency:
            mention['proficiency_level'] = 'UNDEFINED'
        years = mention.get('minimum_years') or 0
        if not isinstance(years, (int, float)) or years < 0 or years > 50:
            mention['minimum_years'] = 0
        # A quote is compared against the source, so it must survive as typed;
        # only the skill name is prose the platform will display.
        _strip_html_tags(mention, 'skill')

    valid_currencies = {'USD', 'UZS', 'EUR', None}
    if resume.get('salary_currency') not in valid_currencies:
        resume['salary_currency'] = None

    valid_language_levels = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}
    for lang_cert in resume.get('language_certificates_data', []):
        level = lang_cert.get('level')
        if level and level not in valid_language_levels:
            lang_cert['level'] = 'A1'

    # --- XSS: strip HTML tags from all free-text fields -----------------------
    _strip_html_tags(resume, 'description')
    _strip_html_tags(resume, 'position')
    _strip_html_tags(resume, 'current_company_name')
    _strip_html_tags(resume, 'current_position')
    for exp in resume.get('experiences_data', []):
        _strip_html_tags(exp, 'description')
        _strip_html_tags(exp, 'company')
        _strip_html_tags(exp, 'role')
    for cert in resume.get('certificates_data', []):
        _strip_html_tags(cert, 'name')
        _strip_html_tags(cert, 'issuing_organization')
        _strip_html_tags(cert, 'credential_url')
    profile = result.get('candidate_profile', {})
    if isinstance(profile, dict):
        for field in ('full_name', 'email', 'phone', 'address', 'linkedin', 'github', 'portfolio'):
            _strip_html_tags(profile, field)


def sanitize_plain_text(value: str) -> str:
    """
    Turn AI free text into safe **plain** text.

    ``bleach.clean`` strips tags but HTML-escapes what remains, so a title like
    "Founder & CEO" comes back as "Founder &amp; CEO" and renders literally in
    the UI. Fields here are stored and displayed as plain text, so entities are
    resolved again after cleaning.

    Unescaping first (to a fixed point) means nested encodings such as
    ``&amp;lt;script&gt;`` are decoded into real markup *before* cleaning, so
    bleach actually removes them instead of passing the encoded form through.
    After cleaning no markup remains, so the final unescape cannot resurrect a
    tag.
    """
    text = value
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped

    text = bleach.clean(text, tags=[], strip=True, strip_comments=True)
    return html.unescape(text).strip()


def _strip_html_tags(obj: dict, field: str) -> None:
    """Sanitize a field value — strip HTML tags and dangerous content."""
    val = obj.get(field)
    if val and isinstance(val, str):
        obj[field] = sanitize_plain_text(val)








def map_ai_response_to_database(
    ai_response: dict[str, Any],
    source_text: str = "",
    created_by: Any = None,
) -> dict[str, Any]:
    """
    Turn a parsed resume into database entities.

    Skills arrive as mentions — a verbatim quote plus a standard English name —
    and are resolved here rather than by the model. Each mention is checked
    against the source it claims to come from, resolved to a stored skill (or a
    new one pending review), and only then kept.

    Args:
        ai_response: Parsed model output
        source_text: Original source content, for checking quotes
        created_by: User to attribute newly created skills to. Without one, a
            skill the platform lacks is dropped rather than queued.

    Returns:
        Mapped data with database IDs
    """
    result = {
        'source_type': ai_response.get('source_type', 'unknown'),
        'detected_language': ai_response.get('detected_language', 'en'),
        'candidate_profile': ai_response.get('candidate_profile', {}),
        'resume': {},
        'mapping_metadata': {
            'skills_matched': [],
            'skills_unmatched': [],
            'skills_hallucinated': [],
            'skills_created': [],
            'skills_over_limit': [],
            'skills_domain_filtered': [],
            'domain_matched': None,
            'languages_matched': [],
            'languages_unmatched': [],
        },
    }

    resume_data = ai_response.get('resume', {})
    metadata = result['mapping_metadata']

    _map_domain_from_ai(resume_data, result)

    resolver = SkillResolver(
        created_by=created_by, language=result['detected_language'],
    )
    kept: list[dict] = []
    seen_ids: set = set()

    for mention in ai_response.get('skill_mentions') or []:
        if not isinstance(mention, dict):
            continue

        name = (mention.get('skill') or '').strip()
        quote = mention.get('quote')
        if not name:
            continue

        if len(kept) >= MAX_GENERATED_SKILLS:
            metadata['skills_over_limit'].append(name)
            continue

        # Provenance: the quote is copied from the source, so it can be checked
        # in any language. This is the whole hallucination defence — a skill
        # nobody wrote about cannot produce a quote that is really there.
        if not verify_evidence_quote(quote, source_text):
            logger.info(
                "Skill '%s' dropped — its quote is not in the source (%r)",
                name, str(quote)[:80],
            )
            metadata['skills_hallucinated'].append({'original': name, 'quote': quote})
            continue

        skill, created = resolver.resolve(name)
        if not skill:
            logger.info("Skill '%s' matched no stored skill and was not created", name)
            metadata['skills_unmatched'].append(name)
            continue

        if skill['id'] in seen_ids:
            continue
        seen_ids.add(skill['id'])

        kept.append({
            'skill_id': skill['id'],
            'skill_name': skill['name'],
            'minimum_years': mention.get('minimum_years') or 0,
            'proficiency_level': mention.get('proficiency_level') or 'UNDEFINED',
        })
        metadata['skills_matched'].append({'original': name, 'matched': skill['name']})
        if created:
            metadata['skills_created'].append(skill['name'])

    result['resume']['skills_data'] = kept

    _backfill_minimum_years(result['resume'])
    _derive_proficiency_levels(result['resume'])

    ai_languages = resume_data.get('language_certificates_data', [])
    result['resume']['language_certificates_data'] = []

    for ai_lang in ai_languages:
        lang_name = ai_lang.get('language_name', '')
        lang_match = LanguageMatcher.find_matching_language(
            lang_name, ai_lang.get('language_code'),
        )

        if lang_match:
            result['resume']['language_certificates_data'].append({
                'language_id': lang_match['id'],
                'language_name': lang_match['name'],
                'level': ai_lang.get('level', 'A1'),
            })
            metadata['languages_matched'].append({
                'original': lang_name,
                'matched': lang_match['name'],
            })
        else:
            metadata['languages_unmatched'].append(lang_name)

    for field in [
        'description', 'position', 'work_status',
        'current_company_name', 'current_position', 'employment_start_date',
        'current_salary', 'salary_currency', 'salary_hide',
        'experiences_data', 'certificates_data',
    ]:
        if field in resume_data:
            result['resume'][field] = resume_data[field]

    # Validate URL fields to prevent XSS via javascript: URIs
    candidate_profile = result.get('candidate_profile', {})
    for url_field in ['linkedin', 'github', 'portfolio']:
        if url_field in candidate_profile and candidate_profile[url_field]:
            value = str(candidate_profile[url_field]).strip()
            if not value.startswith(('http://', 'https://')):
                candidate_profile[url_field] = None

    return result


def _derive_proficiency_levels(resume: dict) -> None:
    """
    Fill in proficiency from years of experience.

    The model leaves this UNDEFINED whenever the source does not spell out a
    level, which is nearly always — resumes say "3+ года", not "advanced". The
    mapping is arithmetic, so it belongs here rather than in a prompt rule the
    model may or may not apply consistently.
    """
    thresholds = (
        (6, 'EXPERT'),
        (3, 'ADVANCED'),
        (1, 'INTERMEDIATE'),
        (0, 'BEGINNER'),
    )

    for skill in resume.get('skills_data', []):
        if skill.get('proficiency_level') not in (None, '', 'UNDEFINED'):
            continue

        years = skill.get('minimum_years') or 0
        if years <= 0:
            continue

        for minimum, level in thresholds:
            if years >= minimum:
                skill['proficiency_level'] = level
                break


def _backfill_minimum_years(resume: dict) -> None:
    """
    Defensive fallback: compute ``minimum_years`` from experience dates
    for any skill where the AI returned 0 or left it unset.

    Uses proficiency level as a weight to distribute years more realistically
    (EXPERT gets more years than BEGINNER), rather than equal distribution.
    """
    skills = resume.get('skills_data', [])
    experiences = resume.get('experiences_data', [])

    zero_years = [s for s in skills if not s.get('minimum_years')]
    if not zero_years or not experiences:
        return

    # Collect all non-overlapping date spans from experiences
    spans: list[tuple[datetime.date, datetime.date]] = []
    for exp in experiences:
        sd = exp.get('start_date')
        if not sd:
            continue
        try:
            start = datetime.date.fromisoformat(sd)
        except (ValueError, TypeError):
            continue
        try:
            end = datetime.date.fromisoformat(exp['end_date']) if exp.get('end_date') else datetime.date.today()
        except (ValueError, TypeError):
            end = datetime.date.today()
        spans.append((start, end))

    if not spans:
        return

    # Sort by start date and merge overlapping spans
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    # Total career span in years (sum of merged spans)
    total_days = sum((end - start).days for start, end in merged)
    if total_days < 30:
        return

    # Distribute years by proficiency weight, not equal split
    PROFICIENCY_WEIGHT = {
        'EXPERT': 3.0,
        'ADVANCED': 2.0,
        'INTERMEDIATE': 1.0,
        'BEGINNER': 0.5,
        'UNDEFINED': 0.8,
    }
    total_years = round(total_days / 365.25, 1)
    total_weight = sum(
        PROFICIENCY_WEIGHT.get(s.get('proficiency_level', 'UNDEFINED'), 0.8)
        for s in zero_years
    ) or 1.0

    for s in zero_years:
        weight = PROFICIENCY_WEIGHT.get(s.get('proficiency_level', 'UNDEFINED'), 0.8)
        s['minimum_years'] = max(1, round(total_years * weight / total_weight))


MIN_EVIDENCE_LENGTH = 4
MAX_EVIDENCE_LENGTH = 300

# Models re-type a quote rather than copy it: punctuation moves, an ellipsis
# appears, a word comes back in a different case. Demanding a byte-exact
# substring throws away real evidence over those edits, so a quote also passes
# when this share of its words is present in the source. A fabricated quote
# fails it — invented sentences bring their own vocabulary.
MIN_EVIDENCE_WORD_COVERAGE = 0.75


def verify_evidence_quote(evidence: Any, source_text: str) -> bool:
    """
    Check that a model-supplied quote really occurs in the source text.

    This is the one anti-hallucination check that works across languages: the
    model justifies an English skill name with the Russian clause it came from,
    and we confirm the clause is genuinely there. It cannot confirm that the
    quote *implies* the skill — that judgement stays with the model — but it
    does make the citation impossible to fabricate.

    Whitespace is normalized on both sides because line wrapping in extracted
    PDF text rarely survives a round trip through the model.

    Args:
        evidence: The quote from the AI response (any type; non-strings fail)
        source_text: Original source content

    Returns:
        ``True`` when the quote is present and of a sensible length.
    """
    if not evidence or not isinstance(evidence, str) or not source_text:
        return False

    quote = _WHITESPACE_RE.sub(' ', evidence).strip().lower()
    if not MIN_EVIDENCE_LENGTH <= len(quote) <= MAX_EVIDENCE_LENGTH:
        return False

    haystack = _WHITESPACE_RE.sub(' ', source_text).lower()
    if quote in haystack:
        return True

    return _quote_words_present(quote, haystack)


def _quote_words_present(quote: str, haystack: str) -> bool:
    """
    Fall back to word coverage when a quote is not a byte-exact substring.

    Words are compared against source words sharing a three-character prefix,
    which absorbs the ending changes a re-typed Russian phrase picks up
    ("переводы"/"переводов") while keeping the comparison cheap — matching every
    quote word against every source word would be quadratic on a long resume.
    """
    words = [w for w in re.findall(r'\w+', quote) if len(w) > 2]
    if not words:
        return False

    source_words = set(re.findall(r'\w+', haystack))
    by_prefix: dict[str, list[str]] = {}
    for word in source_words:
        by_prefix.setdefault(word[:3], []).append(word)

    hits = 0
    for word in words:
        if word in source_words or any(
            _similarity(word, candidate) >= MIN_TOKEN_SIMILARITY
            for candidate in by_prefix.get(word[:3], ())
        ):
            hits += 1

    return hits / len(words) >= MIN_EVIDENCE_WORD_COVERAGE












def _map_domain_from_ai(resume_data: dict, result: dict):
    """Map domain from AI response using DomainMatcher."""
    domain_name = resume_data.get('domain_name')
    domain_match = DomainMatcher.find_matching_domain(domain_name)
    if domain_match:
        result['resume']['domain_id'] = domain_match['id']
        result['resume']['domain_name'] = domain_match['name']
        result['mapping_metadata']['domain_matched'] = domain_match
    else:
        result['resume']['domain_name'] = domain_name
