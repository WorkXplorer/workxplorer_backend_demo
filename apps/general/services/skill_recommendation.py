from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch

from apps.general.services.market_skill_cache import (
    DEFAULT_MAX_MISSING_SKILLS,
    DEFAULT_MIN_MISSING_SKILLS,
    aggregate_market_skill_items,
)
from apps.resumes.models import Resume, ResumeSkill
from apps.skills.localization import (
    canonical_market_skill_key,
    clean_market_skill_name,
    clean_text,
    localized_skill_name,
    normalized_key,
)


def get_candidate_resume(user, resume_id=None):
    queryset = (
        Resume.objects.filter(candidate_id=user.id, is_active=True)
        .select_related("domain")
        .prefetch_related(
            Prefetch(
                "resume_skills",
                queryset=ResumeSkill.objects.select_related("skill"),
            )
        )
    )

    if resume_id:
        try:
            return queryset.filter(id=resume_id).first()
        except (DjangoValidationError, ValueError):
            return None

    return queryset.filter(is_main=True).first() or queryset.first()


def candidate_resume_skill_payloads(resume, language=None):
    skills = []
    skill_map = {}

    for resume_skill in resume.resume_skills.all():
        skill_name = clean_text(localized_skill_name(resume_skill.skill, language))
        if not skill_name:
            continue

        payload = {
            "resume_skill_id": resume_skill.id,
            "local_skill_id": resume_skill.skill_id,
            "skill_name": skill_name,
            "minimum_years": resume_skill.minimum_years,
            "proficiency_level": resume_skill.proficiency_level,
            "proficiency_label": resume_skill.get_proficiency_level_display(),
            "in_resume": True,
        }
        skills.append(payload)
        skill_map[normalized_key(skill_name)] = payload

    return skills, skill_map


def find_resume_skill_payload(skill_name, resume_skill_map):
    key = normalized_key(skill_name)
    if not key:
        return None

    if key in resume_skill_map:
        return resume_skill_map[key]

    for resume_key, payload in resume_skill_map.items():
        if resume_key and (key in resume_key or resume_key in key):
            return payload

    return None


def _compact_candidate_skill_item(item):
    return {
        "skill_name": item.get("skill_name"),
        "in_resume": item.get("in_resume", False),
        "proficiency_level": item.get("proficiency_level"),
    }


def build_candidate_domain_skills_payload(
    resume,
    vacancies=None,
    market_skills=None,
    vacancy_index=0,
    language=None,
    skill_limit=20,
    aggregate=True,
    min_missing_skills=DEFAULT_MIN_MISSING_SKILLS,
    max_missing_skills=DEFAULT_MAX_MISSING_SKILLS,
):
    resume_skills, resume_skill_map = candidate_resume_skill_payloads(
        resume,
        language=language,
    )
    resume_canonical_keys = {
        canonical_market_skill_key(payload["skill_name"])
        for payload in resume_skill_map.values()
        if payload.get("skill_name")
    }

    skill_map = {}
    if market_skills is None:
        market_skills = aggregate_market_skill_items(
            vacancies or [],
            vacancy_index=vacancy_index,
            aggregate=aggregate,
        )

    for market_skill in market_skills:
        skill_name = clean_market_skill_name(market_skill.get("skill_name"))
        key = market_skill.get("normalized_skill_name") or canonical_market_skill_key(
            skill_name
        )
        if not key:
            continue
        item = skill_map.setdefault(
            key,
            {
                "skill_name": skill_name,
                "local_skill": market_skill.get("local_skill"),
                "vacancy_count": 0,
            },
        )
        item["vacancy_count"] = max(
            item["vacancy_count"],
            int(market_skill.get("vacancy_count") or 0),
        )

    existing_skills = []
    missing_skills = []
    existing_candidate_keys = set()
    skill_items = sorted(
        skill_map.items(),
        key=lambda item: (-item[1]["vacancy_count"], item[1]["skill_name"].lower()),
    )
    for canonical_key, skill_data in skill_items:
        skill = skill_data["skill_name"]
        resume_skill = (
            None
            if canonical_key not in resume_canonical_keys
            else find_resume_skill_payload(skill, resume_skill_map)
        )
        if not resume_skill and canonical_key in resume_canonical_keys:
            resume_skill = {"skill_name": skill}
        item = {
            "skill_name": skill,
            "local_skill": skill_data.get("local_skill"),
            "vacancy_count": skill_data["vacancy_count"],
            "in_resume": bool(resume_skill),
            "resume_skill_name": resume_skill["skill_name"] if resume_skill else None,
            "proficiency_level": resume_skill.get("proficiency_level") if resume_skill else None,
        }
        if resume_skill:
            existing_skills.append(item)
            existing_candidate_keys.add(canonical_key)
            existing_candidate_keys.add(normalized_key(item["skill_name"]))
        else:
            missing_skills.append(item)

    for resume_skill in resume_skills:
        skill_name = resume_skill["skill_name"]
        candidate_keys = {
            normalized_key(skill_name),
            canonical_market_skill_key(skill_name),
        }
        if existing_candidate_keys & candidate_keys:
            continue
        existing_skills.append(
            {
                "skill_name": skill_name,
                "vacancy_count": 0,
                "in_resume": True,
                "resume_skill_name": skill_name,
                "proficiency_level": resume_skill.get("proficiency_level"),
            }
        )
        existing_candidate_keys.update(key for key in candidate_keys if key)

    max_missing_skills = max(int(max_missing_skills), 1)
    min_missing_skills = max(min(int(min_missing_skills), max_missing_skills), 0)
    missing_take = max_missing_skills
    if len(missing_skills) < min_missing_skills:
        missing_take = len(missing_skills)
    missing_skills = missing_skills[:missing_take]
    existing_skills = existing_skills[: max(skill_limit, 1)]

    return {
        "existing_skills": [
            _compact_candidate_skill_item(item)
            for item in existing_skills
        ],
        "missing_skills": [
            _compact_candidate_skill_item(item)
            for item in missing_skills
        ],
        "summary": {
            "existing_count": len(existing_skills),
            "missing_count": len(missing_skills),
            "total": len(existing_skills) + len(missing_skills),
            "market_skill_count": len(skill_map),
        },
    }
