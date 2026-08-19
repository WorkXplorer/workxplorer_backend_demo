"""
Resolve skill mentions found in a resume to rows in the skill table.

The model reads the source and reports what it saw, in the source's own words
plus a standard English name. Everything after that — deciding which stored
skill a mention means, and creating one when the platform has none — happens
here, in code.

Why the split matters: the previous design asked the model to answer in *our*
vocabulary, so a Russian resume produced Russian names that no amount of string
comparison could relate to English rows, and a 600-line pile of inflection
rules, letter-context regexes and semantic maps grew up trying. Comparing an
English name the model produced against an English name we stored is a problem
string matching can actually solve.
"""

import logging
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)

# A stored skill this short ("C", "R", "Go", "QA") is only ever reachable by an
# exact match. Fuzzy matching on one or two characters is noise: every longer
# name containing the letter would match it.
SHORT_SKILL_MAX_LEN = 2

# Two names describe the same skill only when every word in one has a
# counterpart in the other. A word with no counterpart is what tells the skills
# apart ("CDN" in "CDN Management"). This is how close two words must be to
# count as counterparts — loose enough for "modelling"/"modeling", tight enough
# to keep "java" away from "javascript".
MIN_TOKEN_SIMILARITY = 0.8

# Ceiling on skills created from one resume. A resume that appears to introduce
# more new skills than this is likelier misread than genuinely novel, and every
# creation costs a reviewer's attention.
MAX_SKILLS_CREATED_PER_RESUME = 8

_WHITESPACE_RE = re.compile(r'\s+')


def normalize_skill_name(value: Optional[str]) -> str:
    """Lowercase, collapse whitespace, drop surrounding punctuation. Characters
    that carry meaning inside a name (``+``, ``#``, ``.``) are preserved."""
    if not value or not isinstance(value, str):
        return ''
    normalized = _WHITESPACE_RE.sub(' ', value.strip().lower())
    return normalized.strip(' \t\n-–—_,;:•*()[]{}"\'')


@lru_cache(maxsize=2048)
def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def token_alignment_score(query: str, candidate: str) -> float:
    """
    Score two normalized names by pairing their words.

    Whole-string similarity cannot separate these cases: it rates "Management"
    against "CDN Management" at 0.83 but "CRM" against "CRM Data Entry" at 0.35,
    so no threshold both admits spelling variants and rejects added qualifiers.
    Pairing words does — a qualifier has no counterpart, a spelling variant has.

    Words keep their internal punctuation, so "node.js" is one word.
    """
    query_words = query.split()
    candidate_words = candidate.split()

    if not query_words or len(query_words) != len(candidate_words):
        return 0.0

    remaining = list(candidate_words)
    total = 0.0

    for word in query_words:
        best_score = 0.0
        best_index = -1
        for index, other in enumerate(remaining):
            score = 1.0 if word == other else _similarity(word, other)
            if score > best_score:
                best_score = score
                best_index = index

        if best_score < MIN_TOKEN_SIMILARITY:
            return 0.0

        total += best_score
        remaining.pop(best_index)

    return round(total / len(query_words), 4)


def is_creatable_skill_name(name: str) -> bool:
    """
    Decide whether a name is shaped like a skill worth creating.

    The model may name skills the platform lacks, which means it can also hand
    back a job duty ("разрабатывал спецификации") or a sentence fragment. A
    reviewer's time is the scarce resource, so anything not shaped like a name
    is dropped rather than queued.
    """
    if not name or not isinstance(name, str):
        return False

    cleaned = _WHITESPACE_RE.sub(' ', name.strip())

    if not 2 <= len(cleaned) <= 60:
        return False
    if len(cleaned.split()) > 4:
        return False
    if not any(character.isalpha() for character in cleaned):
        return False

    # Punctuation that belongs to prose, not to a name. Dots are allowed —
    # skills are full of them (Node.js, ASP.NET) — but a dot that ends the text
    # or is followed by a space gives a sentence away.
    if any(character in cleaned for character in ',!?;:”“"()[]{}<>|\\/'):
        return False
    if cleaned.endswith('.') or '. ' in cleaned:
        return False

    return True


def canonical_created_skill_name(name: str) -> str:
    """
    Tidy capitalisation for a name about to become a permanent row.

    Only fully-lowercase alphabetic words are capitalised, which leaves
    acronyms and deliberate spellings intact: BPMN, iOS, C++ and Node.js all
    survive untouched, while "Sequence diagram" becomes "Sequence Diagram".
    """
    words = _WHITESPACE_RE.sub(' ', str(name).strip()).split()
    return ' '.join(
        word.capitalize() if word.isalpha() and word.islower() else word
        for word in words
    )


class SkillResolver:
    """
    Maps skill names onto stored skills, creating rows for genuinely new ones.

    Loads the skill table once per resume — a generation resolves a dozen names
    against the same few hundred rows, so a query per name would be wasteful.
    """

    def __init__(self, created_by: Any = None, language: str = 'en'):
        self.created_by = created_by
        self.language = language
        self.created_count = 0
        self._skills: list[dict] = []
        self._synonyms: list[dict] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return

        from apps.skills.models import Skill, SkillSynonym

        # name_en is a real name field (see apps/skills/localization.py) and is
        # often the only place the English spelling lives.
        self._skills = list(
            Skill.objects.all().values('id', 'name', 'name_en', 'name_ru', 'name_uz')
        )
        self._synonyms = list(
            SkillSynonym.objects.all().values('synonym', 'skill__id', 'skill__name')
        )
        self._loaded = True

    def resolve(self, name: str) -> tuple[Optional[dict], bool]:
        """
        Resolve one skill name.

        Returns ``(skill, created)`` where skill is ``{'id', 'name'}``, or
        ``(None, False)`` when the name matches nothing and cannot be created.
        """
        query = normalize_skill_name(name)
        if not query:
            return None, False

        match = self._match_exact(query) or self._match_fuzzy(query)
        if match:
            return match, False

        return self._create(name)

    def _match_exact(self, query: str) -> Optional[dict]:
        self._load()

        for skill in self._skills:
            for field in ('name', 'name_en', 'name_ru', 'name_uz'):
                if normalize_skill_name(skill.get(field)) == query:
                    return {'id': skill['id'], 'name': skill['name']}

        for synonym in self._synonyms:
            if normalize_skill_name(synonym['synonym']) == query:
                return {'id': synonym['skill__id'], 'name': synonym['skill__name']}

        return None

    def _match_fuzzy(self, query: str) -> Optional[dict]:
        """Nearest stored name by word pairing, for spelling variants."""
        self._load()

        if len(query) <= SHORT_SKILL_MAX_LEN:
            return None  # exact-only; see SHORT_SKILL_MAX_LEN

        best: Optional[dict] = None
        best_score = 0.0

        for skill in self._skills:
            for field in ('name', 'name_en', 'name_ru', 'name_uz'):
                candidate = normalize_skill_name(skill.get(field))
                if not candidate or len(candidate) <= SHORT_SKILL_MAX_LEN:
                    continue
                score = token_alignment_score(query, candidate)
                if score > best_score:
                    best_score = score
                    best = {'id': skill['id'], 'name': skill['name']}

        if best:
            logger.info("Skill '%s' fuzzy-matched '%s' (%.2f)", query, best['name'], best_score)
        return best

    def _create(self, name: str) -> tuple[Optional[dict], bool]:
        """
        Create a skill pending review, the way the skill endpoint does.

        ``is_active=False`` and an attributed author put the row in front of the
        nightly ``validate_passive_skills`` job, which approves, deduplicates
        and translates it — so nothing here decides whether a skill is
        legitimate, only whether it is plausibly a skill name.
        """
        if not self.created_by:
            return None, False
        if self.created_count >= MAX_SKILLS_CREATED_PER_RESUME:
            logger.info("Skill '%s' not created — per-resume creation limit reached", name)
            return None, False
        if not is_creatable_skill_name(name):
            logger.info("Skill '%s' not created — not shaped like a skill name", name)
            return None, False

        from django.db import IntegrityError
        from apps.skills.localization import normalize_language, skill_create_kwargs
        from apps.skills.models import Skill

        canonical = canonical_created_skill_name(_WHITESPACE_RE.sub(' ', name.strip()))
        create_kwargs = skill_create_kwargs(canonical, normalize_language(self.language))

        try:
            skill = Skill.objects.create(
                is_active=False, created_by=self.created_by, **create_kwargs,
            )
        except IntegrityError:
            # Another resume queued the same new skill first.
            self._loaded = False
            return self._match_exact(normalize_skill_name(canonical)), False

        self.created_count += 1
        self._loaded = False  # so a repeated mention resolves to the new row
        logger.info("Created pending skill '%s' (id=%s)", canonical, skill.id)
        return {'id': skill.id, 'name': skill.name}, True
