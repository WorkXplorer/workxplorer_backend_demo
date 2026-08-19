"""
Skill validation service.

Orchestrates AI-powered validation of passive (inactive) skills:
- Checks if skills are valid, ethical, and legitimate.
- Detects duplicates among existing active skills.
- Provides translations into all three supported languages.
"""

import json
import logging
from difflib import SequenceMatcher
from typing import Any

from django.db import transaction

from apps.skills.models import Skill

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


def validate_passive_skills(ai_client: Any) -> dict[str, Any]:
    """
    Validate all passive skills using the provided AI client.

    Skills are processed in batches of ``_BATCH_SIZE`` to avoid token limits.

    Flow:
    1. Fetch all inactive skills.
    2. Pre-compute similar skills for each (top-3 by string similarity),
       searching both already-active skills and other still-pending
       submissions, so the AI can catch two independently-submitted passive
       duplicates against each other in the same run.
    3. Build a compact prompt per batch and send to AI.
    4. AI returns approval status, translations, and duplicate flags.
    5. Save approved, non-duplicate skills with translations; rejected and
       duplicate skills are deleted/merged, in the order the AI returned
       them.

    Args:
        ai_client: An object with cached_completion() and parse_json_response()
                   methods (GroqClient).

    Returns:
        Dict with summary: {approved, rejected, duplicates, details}.
    """
    passive_qs = Skill.objects.filter(is_active=False).only(
        "id", "name", "name_ru", "name_uz"
    )
    passive_skills = list(passive_qs)

    if not passive_skills:
        return {
            "message": "No passive skills found for validation.",
            "approved": 0,
            "rejected": 0,
            "duplicates": 0,
            "details": [],
        }

    active_skills = _fetch_active_skills()
    comparison_pool = active_skills + passive_skills

    enriched = []
    for ps in passive_skills:
        similar = _find_similar_skills(ps, comparison_pool, top_n=3)
        enriched.append({"skill": ps, "similar": similar})

    all_results = []
    for i in range(0, len(enriched), _BATCH_SIZE):
        batch = enriched[i : i + _BATCH_SIZE]
        prompt = _build_validation_prompt(batch)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        logger.info(
            "Validating batch %d–%d (%d skills)",
            i, i + len(batch) - 1, len(batch),
        )

        raw_response = ai_client.cached_completion(
            messages, "skill_validation", prompt, json_mode=True
        )
        content = raw_response["choices"][0]["message"]["content"]
        try:
            parsed = ai_client.parse_json_response(content)
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse AI response for batch %d–%d: %s",
                i, i + len(batch) - 1, str(exc),
            )
            raise RuntimeError(
                f"AI returned invalid JSON for batch starting at {i}. "
                f"Raw output: {content[:500]}"
            ) from exc

        all_results.extend(parsed.get("skills", []))

    return _process_results(all_results, passive_skills)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a skill taxonomy validator for the WorkXplorer job platform \
(Uzbekistan). Evaluate each submitted skill name.

For each skill, determine:
1. VALIDITY: Is this a real, legitimate professional skill? Reject:
   - Nonsense, gibberish, or placeholder text
   - Offensive, discriminatory, or unethical content
   - Company names, person names, or other non-skill terms
   - Skills that are overly vague (e.g., "good", "stuff")
2. DUPLICATES: Compare against the provided similar_skills list, which may
   include both already-approved skills and other skills submitted by
   different users that are still awaiting approval in this same batch. If
   the submitted name refers to the exact same skill, mark it as a
   duplicate. When several submitted skills in this batch are duplicates of
   each other, approve exactly one of them and mark the rest as duplicates
   of that one — never mark two skills as duplicates of each other.
3. TRANSLATIONS: Provide accurate professional translations in English (en),
   Russian (ru), and Uzbek (uz). If the name is a proper noun or universally
   recognised term (e.g., "Python", "AWS"), keep it the same across languages.
4. DESCRIPTION: Write a concise, one-line description in all three languages.

Respond with a single JSON object containing a "skills" array:
{
  "skills": [
    {
      "skill_id": 123,
      "approved": true,
      "duplicate_of_skill_id": null,
      "name_en": "...",
      "name_ru": "...",
      "name_uz": "...",
      "description_en": "...",
      "description_ru": "...",
      "description_uz": "...",
      "reason": "Brief explanation"
    }
  ]
}

Output raw JSON only — no markdown, no explanations outside the JSON."""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_validation_prompt(enriched: list[dict]) -> str:
    """
    Build the user prompt with passive skills and their similar matches.

    Only top-N similar skills are included to keep token usage low.
    """
    items = []
    for entry in enriched:
        ps = entry["skill"]
        similar = entry["similar"]

        items.append({
            "skill_id": ps.id,
            "submitted_name": ps.name or "",
            "similar_skills": [
                {"id": sid, "name": sname}
                for sid, sname, _ in similar
            ],
        })

    return json.dumps({"skills": items}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Similarity detection
# ---------------------------------------------------------------------------

def _fetch_active_skills():
    """Fetch all active skills, cached for request duration."""
    return list(
        Skill.objects.filter(is_active=True)
        .only("id", "name", "name_ru", "name_uz")
    )


def _normalize(text):
    """Normalize text for comparison."""
    return (text or "").lower().strip()


def _find_similar_skills(passive_skill, candidate_skills, top_n=3):
    """
    Find top-N most similar skills (active or still-pending) using SequenceMatcher.

    Compares against name, name_ru, and name_uz fields.
    """
    submitted = _normalize(passive_skill.name)
    if not submitted:
        return []

    candidates = []
    for candidate in candidate_skills:
        if candidate.id == passive_skill.id:
            continue

        best = 0.0
        for field in ("name", "name_ru", "name_uz"):
            val = _normalize(getattr(candidate, field, None))
            if val:
                best = max(best, SequenceMatcher(None, submitted, val).ratio())

        if best > 0.4:
            candidates.append((candidate.id, candidate.name, best))

    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[:top_n]


# ---------------------------------------------------------------------------
# Result processing
# ---------------------------------------------------------------------------

def _process_results(
    results: list[dict[str, Any]],
    passive_skills: list,
) -> dict[str, Any]:
    """
    Process AI validation results: save approved skills, track stats.

    Runs in two passes so merge correctness never depends on the order the AI
    listed results in. Pass 1 saves and activates every non-duplicate
    approval; pass 2 resolves rejections and duplicates. This guarantees that
    when a duplicate's canonical skill was itself a pending skill approved in
    the same batch, it is already ``is_active=True`` by the time
    ``_remove_duplicate_skill`` looks it up — regardless of whether the AI
    listed the canonical before or after the duplicate.
    """
    passive_by_id = {s.id: s for s in passive_skills}

    approved = 0
    rejected = 0
    duplicates = 0
    details: list[dict[str, Any] | None] = [None] * len(results)

    approval_indices = []
    resolution_indices = []
    for idx, item in enumerate(results):
        if item.get("approved", False) and item.get("duplicate_of_skill_id") is None:
            approval_indices.append(idx)
        else:
            resolution_indices.append(idx)

    # Pass 1: approvals — activates canonical skills before any merge runs.
    for idx in approval_indices:
        item = results[idx]
        skill_id = item.get("skill_id")
        detail = {
            "skill_id": skill_id,
            "approved": True,
            "duplicate_of_skill_id": None,
            "name_en": item.get("name_en", ""),
            "reason": item.get("reason", ""),
        }

        skill = passive_by_id.get(skill_id)
        if skill is None:
            detail["error"] = "Skill not found in database"
        else:
            try:
                _save_approved_skill(skill, item)
                approved += 1
            except Exception as exc:
                logger.error("Failed to save skill %d: %s", skill_id, exc)
                detail["error"] = str(exc)
        details[idx] = detail

    # Pass 2: rejections and duplicates.
    for idx in resolution_indices:
        item = results[idx]
        skill_id = item.get("skill_id")
        is_approved = item.get("approved", False)
        dup_id = item.get("duplicate_of_skill_id")

        detail = {
            "skill_id": skill_id,
            "approved": is_approved,
            "duplicate_of_skill_id": dup_id,
            "name_en": item.get("name_en", ""),
            "reason": item.get("reason", ""),
        }

        if not is_approved:
            rejected += 1
            skill = passive_by_id.get(skill_id)
            if skill is not None:
                try:
                    _delete_skill(skill)
                    detail["deleted"] = True
                except Exception as exc:
                    logger.error(
                        "Failed to delete rejected skill %s: %s", skill_id, exc
                    )
                    detail["error"] = str(exc)
            details[idx] = detail
            continue

        # Approved with a duplicate target.
        duplicates += 1
        skill = passive_by_id.get(skill_id)
        if skill is not None:
            try:
                _remove_duplicate_skill(skill, dup_id)
                detail["deleted"] = True
            except Exception as exc:
                logger.error(
                    "Failed to remove duplicate skill %s: %s", skill_id, exc
                )
                detail["error"] = str(exc)
        details[idx] = detail

    return {
        "message": (
            f"Validation complete: {approved} approved, "
            f"{rejected} rejected, {duplicates} duplicates found."
        ),
        "approved": approved,
        "rejected": rejected,
        "duplicates": duplicates,
        "details": details,
    }


@transaction.atomic
def _save_approved_skill(skill, item: dict[str, Any]) -> None:
    """
    Save an approved skill with AI-provided translations.

    Uses a transaction to ensure consistency.
    """
    skill.name = item.get("name_en", skill.name) or skill.name
    skill.name_ru = item.get("name_ru", "") or skill.name_ru or skill.name
    skill.name_uz = item.get("name_uz", "") or skill.name_uz or skill.name
    skill.description = (
        item.get("description_en", "") or skill.description or ""
    )
    skill.description_ru = (
        item.get("description_ru", "") or skill.description_ru or ""
    )
    skill.description_uz = (
        item.get("description_uz", "") or skill.description_uz or ""
    )
    skill.is_active = True
    skill.save()

    logger.info(
        "Skill #%d approved and activated: name=%s, name_ru=%s, name_uz=%s",
        skill.id,
        skill.name,
        skill.name_ru,
        skill.name_uz,
    )


def _delete_skill(skill) -> None:
    """
    Delete a rejected skill.

    Any resume that references this skill loses it via the ResumeSkill
    ``on_delete=CASCADE`` relation — intended, since rejected skills are
    invalid, offensive, or non-existent.
    """
    skill_id = skill.id
    skill.delete()
    logger.info("Skill #%d deleted by AI validation.", skill_id)


@transaction.atomic
def _remove_duplicate_skill(skill, canonical_id: int) -> None:
    """
    Remove a duplicate skill, preserving candidate data where possible.

    Resume references to the duplicate are re-pointed to the canonical (already
    active) skill before the duplicate is deleted. Resumes that already list the
    canonical skill are skipped (the unique ``resume + skill`` constraint) and
    those stray references are dropped when the duplicate is deleted.
    """
    from apps.resumes.models import ResumeSkill

    canonical = Skill.objects.filter(id=canonical_id, is_active=True).first()
    if canonical is None:
        # Canonical no longer exists/active — nothing to merge into; just delete.
        _delete_skill(skill)
        return

    resumes_with_canonical = set(
        ResumeSkill.objects.filter(skill_id=canonical_id).values_list(
            "resume_id", flat=True
        )
    )
    for resume_skill in ResumeSkill.objects.filter(skill=skill):
        if resume_skill.resume_id in resumes_with_canonical:
            continue
        resume_skill.skill = canonical
        resume_skill.save(update_fields=["skill"])
        resumes_with_canonical.add(resume_skill.resume_id)

    _delete_skill(skill)
