"""
AI Evaluation Service for candidate-vacancy matching.

Uses the AI provider to evaluate a candidate against a specific vacancy,
collecting data from resume, GitHub, LMS (Vault), and portfolio.
"""

import json
import logging
import re
from typing import Optional

import requests
from django.conf import settings

from apps.ai.services.ai_provider_client import AIProviderClient
from utils.prompt_sanitizer import sanitize_prompt_value

logger = logging.getLogger(__name__)

TECH_DOMAIN_KEYWORDS = [
    "information technology", "it", "software", "programming",
    "development", "engineering", "computer science", "web",
    "mobile", "data science", "machine learning", "ai",
    "artificial intelligence", "devops", "cloud", "cybersecurity",
    "security", "backend", "frontend", "full stack", "fullstack",
    "database", "infrastructure", "tech",
    "telecommunications", "telecom", "networking",
    "qa", "testing", "quality assurance",
    "gaming", "game development",
    "embedded", "embedded systems",
    "robotics",
    "blockchain", "web3",
    "analytics", "data analytics", "business intelligence",
    "fintech",
    "edtech",
    "automation",
    "systems", "system administration",
]


def fetch_vault_grades(student_id: str) -> Optional[dict]:
    """
    Fetch LMS grade data from the Vault service.

    Args:
        student_id: The candidate/student ID.

    Returns:
        Grades dict on success, None on failure.
    """
    try:
        url = f"{settings.VAULT_SERVICE_URL}/grades/{student_id}"
        resp = requests.get(
            url,
            headers={"X-Vault-Token": settings.VAULT_TOKEN},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch Vault grades for {student_id}: {e}")
    return None


def _build_vacancy_context(vacancy) -> str:
    """Build a rich text description of the vacancy for the AI prompt."""
    parts = [f"Job Title: {vacancy.title}"]

    if vacancy.domain:
        parts.append(f"Domain: {vacancy.domain.name}")

    if vacancy.company:
        parts.append(f"Company: {vacancy.company.name}")

    if vacancy.location:
        parts.append(f"Location: {vacancy.location}")

    if vacancy.employment_type:
        parts.append(f"Employment Type: {vacancy.employment_type}")

    if vacancy.experience:
        parts.append(f"Required Experience: {vacancy.experience} years")

    if vacancy.salary_min or vacancy.salary_max:
        salary_parts = []
        if vacancy.salary_min:
            salary_parts.append(str(vacancy.salary_min))
        if vacancy.salary_max:
            salary_parts.append(str(vacancy.salary_max))
        currency = getattr(vacancy, "salary_currency", "UZS")
        parts.append(f"Salary Range: {' - '.join(salary_parts)} {currency}")

    if vacancy.requirements:
        requirements = re.sub(r"<[^>]+>", " ", vacancy.requirements).strip()
        parts.append(f"Requirements:\n{requirements}")

    if vacancy.responsibilities:
        responsibilities = re.sub(r"<[^>]+>", " ", vacancy.responsibilities).strip()
        parts.append(f"Responsibilities:\n{responsibilities}")

    if vacancy.about_us:
        about = re.sub(r"<[^>]+>", " ", vacancy.about_us).strip()
        parts.append(f"About the Company:\n{about}")

    # Required skills via VacancySkill through-model
    try:
        skills = vacancy.vacancyskill_set.select_related("skill").all()
        if skills:
            required = [vs.skill.name for vs in skills if vs.is_required]
            optional = [vs.skill.name for vs in skills if not vs.is_required]
            if required:
                parts.append(f"Required Skills: {', '.join(required)}")
            if optional:
                parts.append(f"Nice-to-have Skills: {', '.join(optional)}")
    except Exception as e:
        logger.warning(f"Could not fetch vacancy skills: {e}")

    return "\n\n".join(parts)


def _build_candidate_context(application) -> str:
    """Build a text description of the candidate's profile and resume."""
    parts = []

    candidate = application.candidate

    # Basic candidate info
    parts.append(f"Candidate Email: {candidate.email}")

    # Candidate profile
    profile = None
    try:
        profile = getattr(candidate, "candidateprofile", None)
        if profile is None:
            from apps.profiles.models import CandidateProfile
            profile = CandidateProfile.objects.filter(candidate=candidate).first()
        if profile:
            if profile.full_name:
                parts.append(f"Name: {profile.full_name}")
            if profile.address:
                parts.append(f"Location: {profile.address}")
    except Exception as e:
        logger.warning(f"Could not load candidate profile: {e}")

    # Resume data
    resume = application.resume_used
    if resume is None:
        # Fall back to candidate's main resume
        try:
            from apps.resumes.models import Resume
            resume = Resume.objects.filter(
                candidate=candidate, is_main=True
            ).prefetch_related("resume_skills__skill", "experiences").first()
            if resume is None:
                resume = Resume.objects.filter(
                    candidate=candidate
                ).prefetch_related("resume_skills__skill", "experiences").order_by("-created_at").first()
        except Exception as e:
            logger.warning(f"Could not fetch resume for candidate {candidate.id}: {e}")

    if resume:
        if resume.title:
            parts.append(f"Resume Title: {resume.title}")
        if resume.position:
            parts.append(f"Desired Position: {resume.position}")
        if resume.description:
            parts.append(f"Profile Summary:\n{resume.description}")
        if resume.work_status:
            parts.append(f"Work Status: {resume.work_status}")
        if resume.current_position:
            parts.append(f"Current Position: {resume.current_position}")
        if resume.current_company_name:
            parts.append(f"Current Company: {resume.current_company_name}")

        # Skills
        try:
            skills = resume.resume_skills.select_related("skill").all()
            if skills:
                skill_strs = []
                for rs in skills:
                    skill_str = rs.skill.name
                    if rs.minimum_years:
                        skill_str += f" ({rs.minimum_years}y)"
                    if rs.proficiency_level and rs.proficiency_level != "UNDEFINED":
                        skill_str += f" [{rs.proficiency_level}]"
                    skill_strs.append(skill_str)
                parts.append(f"Skills: {', '.join(skill_strs)}")
        except Exception as e:
            logger.warning(f"Could not fetch resume skills: {e}")

        # Experiences
        try:
            experiences = resume.experiences.all()
            if experiences:
                exp_parts = ["Work Experience:"]
                for exp in experiences:
                    exp_line = f"  - {exp.role} at {exp.company}"
                    if exp.start_date:
                        end = str(exp.end_date) if exp.end_date else "present"
                        exp_line += f" ({exp.start_date} to {end})"
                    if exp.description:
                        exp_line += f"\n    {exp.description[:300]}"
                    exp_parts.append(exp_line)
                parts.append("\n".join(exp_parts))
        except Exception as e:
            logger.warning(f"Could not fetch resume experiences: {e}")

        # Language certificates
        try:
            lang_certs = resume.language_certificates.select_related("language").all()
            if lang_certs:
                langs = [f"{lc.language.name} ({lc.level})" for lc in lang_certs]
                parts.append(f"Languages: {', '.join(langs)}")
        except Exception as e:
            logger.warning(f"Could not fetch language certs: {e}")

        # General certificates
        try:
            certs = resume.certificates.all()
            if certs:
                cert_lines = ["Certificates:"]
                for cert in certs:
                    cert_line = f"  - {cert.name}"
                    if cert.issuing_organization:
                        cert_line += f" ({cert.issuing_organization})"
                    if cert.issue_date:
                        cert_line += f" - {cert.issue_date}"
                    cert_lines.append(cert_line)
                parts.append("\n".join(cert_lines))
        except Exception as e:
            logger.warning(f"Could not fetch resume certificates: {e}")

    # Cover letter from application
    if application.cover_letter:
        parts.append(f"Cover Letter:\n{application.cover_letter}")

    # Portfolio URL (from application or profile)
    portfolio = getattr(application, "portfolio_url", None)
    if portfolio:
        parts.append(f"Portfolio URL: {portfolio}")

    # Education from profile
    try:
        if profile and profile.education:
            edu = profile.education
            edu_parts = []
            if edu.get("university"):
                edu_parts.append(f"University: {edu['university']}")
            if edu.get("faculty"):
                edu_parts.append(f"Faculty: {edu['faculty']}")
            if edu.get("speciality"):
                edu_parts.append(f"Speciality: {edu['speciality']}")
            if edu.get("course"):
                edu_parts.append(f"Course: {edu['course']}")
            if edu_parts:
                parts.append("Education:\n" + "\n".join(edu_parts))
    except Exception as e:
        logger.warning(f"Could not fetch candidate education: {e}")

    # EduPartner affiliation
    try:
        if candidate.edupartner:
            edu_affil_parts = [f"Educational Institution: {candidate.edupartner.name}"]
            if candidate.faculty:
                edu_affil_parts.append(f"Faculty: {candidate.faculty.name}")
            parts.append("Academic Affiliation:\n" + "\n".join(edu_affil_parts))
    except Exception as e:
        logger.warning(f"Could not fetch edupartner data: {e}")

    # Social/Portfolio URL from profile
    try:
        if profile and profile.social_url:
            parts.append(f"Personal Website/Portfolio: {profile.social_url}")
    except Exception as e:
        logger.warning(f"Could not fetch social URL: {e}")

    return "\n\n".join(parts)


def _is_tech_domain(vacancy) -> bool:
    """
    Check if a vacancy belongs to a tech-related domain.
    
    Uses TECH_DOMAIN_KEYWORDS to match against the vacancy domain name
    (case-insensitive). If no domain is set, defaults to True (fetch GitHub)
    to maintain backward compatibility.
    
    Args:
        vacancy: Vacancy instance
        
    Returns:
        True if domain is tech-related or unknown, False otherwise
    """
    if not vacancy.domain or not vacancy.domain.name:
        return True

    domain_lower = vacancy.domain.name.lower()
    for keyword in TECH_DOMAIN_KEYWORDS:
        if len(keyword.split()) > 1:
            if keyword in domain_lower:
                return True
        else:
            if re.search(r'\b' + re.escape(keyword) + r'\b', domain_lower):
                return True
    return False


def _normalize_for_matching(text: str) -> str:
    """Collapse whitespace and lowercase for tolerant substring comparison."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _verify_matched_skills_evidence(evaluation: dict, evidence_source: str) -> dict:
    """
    Deterministically reject any matched_skill whose cited evidence quote is not a
    genuine verbatim substring of the candidate data sent to the model. This guards
    against the LLM marking skills as "matched" via job-title/role inference rather
    than actual evidence, regardless of what the prompt instructs it to do.
    """
    skills_analysis = evaluation.get("skills_analysis")
    if not isinstance(skills_analysis, dict):
        return evaluation

    matched = skills_analysis.get("matched_skills") or []
    evidences = skills_analysis.get("matched_skills_evidence") or []
    missing = list(skills_analysis.get("missing_skills") or [])

    normalized_source = _normalize_for_matching(evidence_source)

    verified_matched = []
    for idx, skill in enumerate(matched):
        quote = evidences[idx] if idx < len(evidences) else ""
        normalized_quote = _normalize_for_matching(str(quote)) if quote else ""
        if len(normalized_quote) >= 3 and normalized_quote in normalized_source:
            verified_matched.append(skill)
        else:
            logger.info(
                "Rejecting matched_skill %r — no verbatim evidence found in candidate data (quote=%r)",
                skill, quote,
            )
            if skill not in missing:
                missing.append(skill)

    skills_analysis["matched_skills"] = verified_matched
    skills_analysis["missing_skills"] = missing
    skills_analysis.pop("matched_skills_evidence", None)
    return evaluation


def evaluate_candidate_for_vacancy(application, language: str = "uz") -> dict:
    """
    Build multi-source context, call the AI provider, and return parsed evaluation JSON.

    Args:
        application: JobApplication instance with related vacancy and candidate loaded.
        language: Language code for the AI response instruction ('uz', 'ru', 'en').

    Returns:
        Dict containing:
            - evaluation: Parsed evaluation dict matching the documented schema
            - usage: Dict with prompt_tokens, completion_tokens, total_tokens

    Raises:
        Exception: If AI call fails or response cannot be parsed.
    """
    vacancy = application.vacancy
    candidate = application.candidate

    # 1. Build vacancy context
    vacancy_context = _build_vacancy_context(vacancy)

    # 2. Build candidate context from resume + profile
    candidate_context = _build_candidate_context(application)

    # 3. Activity context (GitHub + Portfolio + LMS combined)
    activity_parts = []

    # Determine if the vacancy domain is tech-related
    is_tech_role = _is_tech_domain(vacancy)

    # Candidate profile — fetch unconditionally (needed for portfolio fallback)
    profile_for_activity = None
    try:
        from apps.profiles.models import CandidateProfile
        profile_for_activity = CandidateProfile.objects.filter(candidate=candidate).first()
    except Exception as e:
        logger.warning(f"Could not load candidate profile: {e}")

    # GitHub data — only fetch for tech roles to avoid penalizing non-tech candidates
    if is_tech_role:
        try:
            from apps.resumes.services.github_service import fetch_github_data, format_github_context_for_prompt
            if profile_for_activity and profile_for_activity.github_url:
                github_data = fetch_github_data(profile_for_activity.github_url)
                if github_data.get("success"):
                    github_context = format_github_context_for_prompt(github_data)
                    activity_parts.append("GitHub Activity:\n" + github_context)
        except Exception as e:
            logger.warning(f"GitHub data fetch failed: {e}")
    else:
        logger.info(
            "Non-tech domain '%s' — skipping GitHub fetch to avoid penalizing candidate",
            vacancy.domain.name if vacancy.domain else "None",
        )

    # LMS / Vault grades
    try:
        grades = fetch_vault_grades(str(candidate.id))
        if grades:
            lms_context = f"LMS/Academic Performance:\n{json.dumps(grades, ensure_ascii=False, indent=2)}"
            activity_parts.append(lms_context)
    except Exception as e:
        logger.warning(f"Vault grades fetch failed: {e}")

    # Portfolio URL (application portfolio_url or profile social_url)
    portfolio_url = getattr(application, "portfolio_url", None)
    if not portfolio_url and profile_for_activity and profile_for_activity.social_url:
        portfolio_url = profile_for_activity.social_url
    if portfolio_url:
        activity_parts.append(f"Portfolio/Personal Website: {portfolio_url}")

    activity_context = "\n\n".join(activity_parts) if activity_parts else ""

    # 4. Assemble prompt with language instruction
    language_instructions = {
        "uz": "O'zbek tilida javob bering.",
        "ru": "Отвечайте на русском языке.",
        "en": "Respond in English.",
    }
    lang_instruction = language_instructions.get(language, language_instructions["uz"])

    activity_score_guidance = (
        "- activity_score: evaluate GitHub repos/commits, portfolio quality, LMS academic performance, and personal website holistically. Provide specific details."
        if is_tech_role
        else "- activity_score: This is a non-technical role. GitHub activity is not relevant. Evaluate portfolio quality, LMS academic performance, and personal website only. Set score to null if no portfolio or LMS data is available. Do not penalize for lack of GitHub activity."
    )

    system_prompt = f"""You are an expert technical recruiter and hiring evaluator.
Your task is to evaluate a job candidate against a specific vacancy and return a structured JSON assessment.

{lang_instruction}

CRITICAL — ALL text fields MUST be returned in THREE languages (uz, ru, en):
For EVERY string field and list field below, provide values in all three languages.

LANGUAGE RULES (strict — do not violate these):
- The "uz" field MUST be written in MODERN UZBEK LATIN SCRIPT (e.g. "Kandidat", "tajriba", "ko'nikmalar").
  NEVER use Russian/Cyrillic text in the "uz" field.
- The "ru" field MUST be written in RUSSIAN CYRILLIC (e.g. "Кандидат", "опыт", "навыки").
- The "en" field MUST be written in ENGLISH.

Example CORRECT format — follow this exactly:
  "summary": {{
    "uz": "Kandidat CRM tizimlari va PC bilan ishlash ko'nikmalariga ega...",
    "ru": "Кандидат обладает навыками работы с CRM и ПК...",
    "en": "The candidate possesses CRM and PC skills..."
  }},
  "red_flags": {{
    "uz": ["Tajriba yetarli emas"],
    "ru": ["Недостаточно опыта"],
    "en": ["Insufficient experience"]
  }}

You MUST return ONLY a valid JSON object — no markdown, no explanation, no code fences.
The JSON must exactly match this schema:
{{
  "overall_score": <float 0-100>,
  "recommendation": <"HIGHLY_RECOMMENDED" | "RECOMMENDED" | "NEUTRAL" | "NOT_RECOMMENDED">,
  "match_breakdown": {{
    "skills_match": {{
      "score": <float 0-100 or null>,
      "details": [
        {{"uz": "<string in Uzbek>", "ru": "<string in Russian>", "en": "<string in English>"}}
      ]
    }},
    "experience_match": {{
      "score": <float 0-100 or null>,
      "details": [
        {{"uz": "<string in Uzbek>", "ru": "<string in Russian>", "en": "<string in English>"}}
      ]
    }},
    "education_match": {{
      "score": <float 0-100 or null>,
      "details": [
        {{"uz": "<string in Uzbek>", "ru": "<string in Russian>", "en": "<string in English>"}}
      ]
    }},
    "activity_score": {{
      "score": <float 0-100 or null>,
      "details": [
        {{"uz": "<string in Uzbek>", "ru": "<string in Russian>", "en": "<string in English>"}}
      ]
    }}
  }},
  "skills_analysis": {{
    "matched_skills": [<list of skill names>],
    "matched_skills_evidence": [<list of verbatim quotes, one per entry in matched_skills, in the
      same order — each quote MUST be copied character-for-character from the CANDIDATE PROFILE
      or ACTIVITY & PORTFOLIO sections below, proving that specific skill>],
    "missing_skills": [<list of skill names>],
    "bonus_skills": [<list of skill names>]
  }},
  "experience_summary": {{
    "uz": <string>,
    "ru": <string>,
    "en": <string>
  }},
  "education_summary": {{
    "uz": <string>,
    "ru": <string>,
    "en": <string>
  }},
  "activity_summary": {{
    "uz": <string>,
    "ru": <string>,
    "en": <string>
  }},
  "summary": {{
    "uz": <string>,
    "ru": <string>,
    "en": <string>
  }},
  "red_flags": {{
    "uz": [<list of strings>],
    "ru": [<list of strings>],
    "en": [<list of strings>]
  }},
  "strengths": {{
    "uz": [<list of strings>],
    "ru": [<list of strings>],
    "en": [<list of strings>]
  }}
}}

Scoring guidance:
- overall_score: weighted average of match_breakdown component scores
- recommendation: HIGHLY_RECOMMENDED (score >= 80), RECOMMENDED (60-79), NEUTRAL (40-59), NOT_RECOMMENDED (< 40)
- Use null for match_breakdown sub-scores when data is unavailable
- Be objective and evidence-based
- education_match: consider university relevance, faculty/speciality alignment, language proficiency (CEFR levels), and additional certificates. Provide specific details.
{activity_score_guidance}
- Each match_breakdown item must contain a "score" (0-100 or null) and a "details" array with 2-4 bullet-point strings
- education_summary and activity_summary MUST be tri-language objects (uz, ru, en)
- Each item inside match_breakdown "details" arrays MUST be a tri-language object with uz/ru/en keys, just like other text fields
- skills_analysis.matched_skills and skills_analysis.missing_skills MUST only contain skill names
  that appear in the vacancy's "Required Skills" / "Nice-to-have Skills" list in the vacancy
  context above. Do not invent or infer additional skills from the free-text requirements,
  responsibilities, or company description, even if they seem relevant — if the vacancy has no
  explicit skills list, leave matched_skills and missing_skills empty.
- A required/nice-to-have skill belongs in matched_skills ONLY if it is explicitly evidenced by
  the candidate's data: it appears in the candidate's "Skills" list (resume_skills), OR it is
  explicitly named in the candidate's work experience descriptions, cover letter, certificates,
  or GitHub activity summary. Do NOT mark a skill as matched merely because it is commonly
  associated with the candidate's job title, role, or industry, and do NOT mark it matched based
  on general assumptions about what someone in that position "probably" knows. If there is no
  explicit textual evidence for a required/nice-to-have skill, it MUST go into missing_skills
  instead, even if the candidate otherwise seems qualified.
- For every skill placed in matched_skills, matched_skills_evidence MUST contain, at the same
  index, an exact verbatim quote (copied character-for-character, do not paraphrase or translate)
  from the CANDIDATE PROFILE or ACTIVITY & PORTFOLIO sections that proves the candidate has that
  skill. A quote implying the skill through job-title stereotypes ("System Analyst roles usually
  require teamwork") is NOT acceptable evidence. If you cannot find a real verbatim quote for a
  skill, you MUST NOT include it in matched_skills — put it in missing_skills instead. Every
  matched skill without valid quoted evidence will be programmatically rejected and moved to
  missing_skills, so only include skills you can genuinely quote.
- skills_analysis.bonus_skills lists the candidate's skills that are NOT in the vacancy's
  required/nice-to-have list (skills the candidate has beyond what's asked for)"""

    user_message_parts = [
        "## VACANCY TO FILL\n" + sanitize_prompt_value(vacancy_context, max_length=20000),
        "## CANDIDATE PROFILE\n" + sanitize_prompt_value(candidate_context, max_length=20000),
    ]
    if activity_context:
        user_message_parts.append("## ACTIVITY & PORTFOLIO\n" + sanitize_prompt_value(activity_context, max_length=10000))

    user_message_parts.append(
        "\nEvaluate this candidate for the vacancy above. "
        "Return ONLY the JSON evaluation object with no additional text."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_message_parts)},
    ]

    # 5. Call the AI provider
    client = AIProviderClient()
    response = client.chat_completion(
        messages=messages,
        temperature=0.1,
        json_mode=True,
        timeout=120,
    )

    # 6. Extract and parse
    raw_text = response["choices"][0]["message"]["content"]
    raw_text = client.strip_code_fence(raw_text)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        result = client.parse_json_response(raw_text)
        if result is None:
            logger.warning("AI provider returned unparseable response (len=%d)", len(raw_text))
            raise ValueError("AI provider returned an unparseable response.")

    evidence_source = candidate_context
    if activity_context:
        evidence_source += "\n" + activity_context
    result = _verify_matched_skills_evidence(result, evidence_source)

    return {
        "evaluation": result,
        "usage": response.get("usage", {}),
    }
