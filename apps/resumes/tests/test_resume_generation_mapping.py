"""
Tests for AI resume-generation post-processing.

The pipeline reads a source into skill *mentions* — a verbatim quote plus a
standard English name — and resolves those to stored skills here in code. These
tests cover the failure modes that reached production while that work lived in
the prompt: junk skills from substring matching ("C", "R", "CRM Data Entry"),
titles rendered as "Founder &amp; CEO", and a Russian resume producing nothing
at all because English skill names cannot be found in Russian text.
"""

from django.test import SimpleTestCase, TestCase

from apps.authentication.models import Candidate
from apps.resumes.services.resume_generation import (
    MAX_GENERATED_SKILLS,
    LanguageMatcher,
    _validate_ai_output,
    get_system_prompt,
    map_ai_response_to_database,
    sanitize_plain_text,
    verify_evidence_quote,
)
from apps.resumes.services.skill_resolution import (
    SkillResolver,
    canonical_created_skill_name,
    is_creatable_skill_name,
    normalize_skill_name,
    token_alignment_score,
)
from apps.skills.models import Skill, SkillSynonym

RUSSIAN_SOURCE = (
    "Системный аналитик, TBC UZ, январь 2023 — октябрь 2025.\n"
    "Занимался системным анализом и проектированием финансовых продуктов, "
    "включая P2P-переводы и международные переводы.\n"
    "Умею и знаю BPMN, Sequence diagram.\n"
    "Также приходилось писать документацию."
)


def mention(skill, quote, years=3, level="ADVANCED"):
    return {
        "skill": skill,
        "quote": quote,
        "minimum_years": years,
        "proficiency_level": level,
    }


class SanitizePlainTextTests(SimpleTestCase):
    def test_ampersand_is_not_html_escaped(self):
        self.assertEqual(sanitize_plain_text("Founder & CEO"), "Founder & CEO")

    def test_pre_escaped_entity_is_decoded(self):
        self.assertEqual(sanitize_plain_text("Founder &amp; CEO"), "Founder & CEO")

    def test_tags_are_stripped(self):
        self.assertEqual(sanitize_plain_text("<b>Backend</b> Developer"), "Backend Developer")

    def test_encoded_script_tag_is_removed(self):
        self.assertNotIn("script>", sanitize_plain_text("&lt;script&gt;alert(1)&lt;/script&gt;X"))

    def test_double_encoded_script_tag_is_removed(self):
        self.assertNotIn("<script>", sanitize_plain_text("&amp;lt;script&amp;gt;alert(1)"))

    def test_validate_ai_output_sanitizes_position(self):
        result = {
            "source_type": "prompt",
            "candidate_profile": {},
            "resume": {"position": "Founder &amp; CEO", "description": "R&amp;D lead"},
        }
        _validate_ai_output(result)
        self.assertEqual(result["resume"]["position"], "Founder & CEO")
        self.assertEqual(result["resume"]["description"], "R&D lead")

    def test_validate_ai_output_normalises_mentions(self):
        result = {
            "source_type": "prompt",
            "candidate_profile": {},
            "skill_mentions": [{"skill": "BPMN", "quote": "BPMN", "minimum_years": 900,
                                "proficiency_level": "WIZARD"}],
            "resume": {},
        }
        _validate_ai_output(result)
        self.assertEqual(result["skill_mentions"][0]["minimum_years"], 0)
        self.assertEqual(result["skill_mentions"][0]["proficiency_level"], "UNDEFINED")


class EvidenceQuoteTests(SimpleTestCase):
    def test_quote_present_in_source(self):
        self.assertTrue(verify_evidence_quote("Занимался системным анализом", RUSSIAN_SOURCE))

    def test_quote_retyped_with_drift_is_accepted(self):
        # Production case: the model re-typed the clause with different
        # punctuation, and the skill was wrongly dropped.
        self.assertTrue(
            verify_evidence_quote("финансовых продуктах, включая P2P-переводы и т.д.", RUSSIAN_SOURCE)
        )

    def test_declined_words_are_accepted(self):
        self.assertTrue(verify_evidence_quote("международных переводов", RUSSIAN_SOURCE))

    def test_invented_quote_is_rejected(self):
        self.assertFalse(verify_evidence_quote("администрировал кластеры Kubernetes", RUSSIAN_SOURCE))

    def test_empty_and_non_string_quotes_are_rejected(self):
        self.assertFalse(verify_evidence_quote("", RUSSIAN_SOURCE))
        self.assertFalse(verify_evidence_quote(None, RUSSIAN_SOURCE))
        self.assertFalse(verify_evidence_quote(["списком"], RUSSIAN_SOURCE))

    def test_trivial_and_oversized_quotes_are_rejected(self):
        self.assertFalse(verify_evidence_quote("UZ", RUSSIAN_SOURCE))
        self.assertFalse(verify_evidence_quote(RUSSIAN_SOURCE * 3, RUSSIAN_SOURCE))


class TokenAlignmentScoreTests(SimpleTestCase):
    def test_extra_qualifier_word_rejects_the_match(self):
        self.assertEqual(token_alignment_score("crm", "crm data entry"), 0.0)
        self.assertEqual(token_alignment_score("management", "cdn management"), 0.0)

    def test_single_letter_never_matches_a_longer_name(self):
        self.assertEqual(token_alignment_score("c", "c++"), 0.0)
        self.assertEqual(token_alignment_score("r", "fundraising"), 0.0)

    def test_spelling_variants_still_match(self):
        self.assertGreater(token_alignment_score("financial modelling", "financial modeling"), 0.9)

    def test_unrelated_words_of_similar_shape_do_not_match(self):
        self.assertEqual(token_alignment_score("java", "javascript"), 0.0)

    def test_normalization_drops_decoration(self):
        self.assertEqual(normalize_skill_name("  • Business  Development, "), "business development")


class CreatableSkillNameTests(SimpleTestCase):
    def test_real_skill_names_are_accepted(self):
        for name in ("BPMN", "UML", "Sequence Diagram", "Apache Kafka", "C++", "Node.js"):
            self.assertTrue(is_creatable_skill_name(name), name)

    def test_job_duties_and_fragments_are_rejected(self):
        for name in (
            "разрабатывал детальные спецификации и диаграммы",
            "Writing specifications for banking services.",
            "", "   ", "12345", "Skills: BPMN, UML (see above)",
        ):
            self.assertFalse(is_creatable_skill_name(name), name)

    def test_capitalisation_is_tidied_without_touching_acronyms(self):
        self.assertEqual(canonical_created_skill_name("Sequence diagram"), "Sequence Diagram")
        for name in ("BPMN", "iOS", "C++", "Node.js", "REST API"):
            self.assertEqual(canonical_created_skill_name(name), name)


class SkillResolverTests(TestCase):
    def setUp(self):
        for name in ["C", "R", "CRM Data Entry", "CDN Management", "Financial Modeling",
                     "JavaScript", "Business Analysis"]:
            Skill.objects.create(name=name)
        SkillSynonym.objects.create(skill=Skill.objects.get(name="JavaScript"), synonym="JS")
        self.resolver = SkillResolver()

    def test_exact_match(self):
        skill, created = self.resolver.resolve("Business Analysis")
        self.assertEqual(skill["name"], "Business Analysis")
        self.assertFalse(created)

    def test_synonym_match(self):
        skill, _ = self.resolver.resolve("JS")
        self.assertEqual(skill["name"], "JavaScript")

    def test_spelling_variant_matches(self):
        skill, _ = self.resolver.resolve("Financial Modelling")
        self.assertEqual(skill["name"], "Financial Modeling")

    def test_single_letter_rows_are_not_reachable_by_longer_names(self):
        for name in ("CRM", "Fundraising", "Customer Research"):
            skill, _ = self.resolver.resolve(name)
            if skill:
                self.assertNotIn(skill["name"], {"C", "R"}, f"{name} matched {skill['name']}")

    def test_qualified_row_is_not_matched_by_a_generic_name(self):
        skill, _ = self.resolver.resolve("Management")
        self.assertIsNone(skill)

    def test_nothing_is_created_without_an_author(self):
        skill, created = self.resolver.resolve("BPMN")
        self.assertIsNone(skill)
        self.assertFalse(created)

    def test_match_existing_never_creates(self):
        resolver = SkillResolver(created_by=Candidate.objects.create_user(
            email="resolver@test.com", password="x", is_candidate=True,
        ))
        self.assertIsNone(resolver.match_existing("BPMN"))
        self.assertFalse(Skill.objects.filter(name="BPMN").exists())


class RussianSourceMappingTests(TestCase):
    """The case that emptied the skills list: a Russian resume, an English
    skill table, and no string metric relating the two."""

    def setUp(self):
        self.candidate = Candidate.objects.create_user(
            email="ru-mapping@test.com", password="x", is_candidate=True,
        )
        analysis = Skill.objects.create(name="System Analysis")
        analysis.name_ru = "Системный анализ"
        analysis.save()
        Skill.objects.create(name="Documentation")

    def _map(self, mentions, created_by=None):
        response = {"source_type": "prompt", "detected_language": "ru",
                    "skill_mentions": mentions, "resume": {}}
        return map_ai_response_to_database(
            response, source_text=RUSSIAN_SOURCE, created_by=created_by,
        )

    def test_english_name_resolves_though_the_source_is_russian(self):
        mapped = self._map([mention("System Analysis", "Занимался системным анализом")])
        self.assertEqual(
            [s["skill_name"] for s in mapped["resume"]["skills_data"]], ["System Analysis"],
        )

    def test_named_tool_absent_from_the_table_is_created_pending(self):
        mapped = self._map(
            [mention("BPMN", "Умею и знаю BPMN, Sequence diagram")],
            created_by=self.candidate,
        )
        created = Skill.objects.get(name="BPMN")
        self.assertFalse(created.is_active)
        self.assertEqual(created.created_by_id, self.candidate.id)
        self.assertEqual(mapped["mapping_metadata"]["skills_created"], ["BPMN"])

    def test_unquoted_skill_is_dropped_as_hallucinated(self):
        mapped = self._map(
            [mention("Kubernetes", "администрировал кластеры Kubernetes")],
            created_by=self.candidate,
        )
        self.assertEqual(mapped["resume"]["skills_data"], [])
        self.assertTrue(mapped["mapping_metadata"]["skills_hallucinated"])
        self.assertFalse(Skill.objects.filter(name="Kubernetes").exists())

    def test_duty_shaped_name_is_not_created(self):
        mapped = self._map(
            [mention("Разрабатывал детальные спецификации и диаграммы",
                     "Умею и знаю BPMN, Sequence diagram")],
            created_by=self.candidate,
        )
        self.assertEqual(mapped["resume"]["skills_data"], [])
        self.assertEqual(mapped["mapping_metadata"]["skills_unmatched"],
                         ["Разрабатывал детальные спецификации и диаграммы"])

    def test_repeated_skill_is_kept_once(self):
        mapped = self._map([
            mention("System Analysis", "Занимался системным анализом"),
            mention("System Analysis", "Системный аналитик"),
        ])
        self.assertEqual(len(mapped["resume"]["skills_data"]), 1)


class SkillLimitTests(TestCase):
    def setUp(self):
        self.names = [f"Skill Number {i:02d}" for i in range(30)]
        for name in self.names:
            Skill.objects.create(name=name)

    def test_generated_skills_are_capped(self):
        source = "\n".join(self.names)
        response = {
            "source_type": "prompt",
            "skill_mentions": [mention(name, name) for name in self.names],
            "resume": {},
        }
        mapped = map_ai_response_to_database(response, source_text=source)

        self.assertEqual(len(mapped["resume"]["skills_data"]), MAX_GENERATED_SKILLS)
        self.assertEqual(
            len(mapped["mapping_metadata"]["skills_over_limit"]),
            len(self.names) - MAX_GENERATED_SKILLS,
        )


class SystemPromptGuidanceTests(SimpleTestCase):
    """The prompt must pull in two directions at once — report everything the
    source shows, invent nothing. Leaning on either alone has broken it before."""

    def test_prompt_asks_for_quoted_mentions(self):
        prompt = get_system_prompt("ru")
        self.assertIn("skill_mentions", prompt)
        self.assertIn("character-for-character", prompt)

    def test_prompt_states_a_target_range(self):
        self.assertIn("8-15 skills", get_system_prompt("ru"))

    def test_prompt_keeps_named_tools_specific(self):
        self.assertIn("Sequence Diagram", get_system_prompt("en"))

    def test_prompt_no_longer_ships_the_skill_vocabulary(self):
        # Listing 800 skills is what made the model generalise BPMN into a
        # listed category; resolution happens in code now.
        self.assertNotIn("AVAILABLE SKILLS", get_system_prompt("ru"))


class LanguageMatchingTests(TestCase):
    def setUp(self):
        from apps.languages.models import Language

        self.english = Language.objects.create(name="English", code="en")
        self.russian = Language.objects.create(name="Русский", code="ru")

    def test_iso_code_matches_whatever_the_name_is_stored_as(self):
        match = LanguageMatcher.find_matching_language("Russian", "ru")
        self.assertEqual(match["id"], self.russian.id)

    def test_localised_name_matches_without_a_code(self):
        match = LanguageMatcher.find_matching_language("Английский")
        self.assertEqual(match["id"], self.english.id)

    def test_unknown_language_is_not_invented(self):
        self.assertIsNone(LanguageMatcher.find_matching_language("Klingon", "tlh"))

    def test_languages_reach_the_resume(self):
        response = {
            "source_type": "prompt",
            "skill_mentions": [],
            "resume": {
                "language_certificates_data": [
                    {"language_name": "Английский", "language_code": "en", "level": "B2"},
                ],
            },
        }
        mapped = map_ai_response_to_database(response, source_text="Английский B2")
        self.assertEqual(
            mapped["resume"]["language_certificates_data"],
            [{"language_id": self.english.id, "language_name": "English", "level": "B2"}],
        )


class DescriptionAndLanguagePromptTests(SimpleTestCase):
    def test_prompt_briefs_a_substantive_summary(self):
        prompt = get_system_prompt("ru")
        self.assertIn("3-5 sentences", prompt)
        # Filler adjectives are what made previous summaries read like anyone.
        self.assertIn("ответственный", prompt)

    def test_prompt_maps_wording_to_cefr_levels(self):
        prompt = get_system_prompt("ru")
        self.assertIn("ISO 639-1", prompt)
        self.assertIn("свободный", prompt)

    def test_prompt_forbids_unmentioned_languages(self):
        self.assertIn("Never list a language the source does not mention", get_system_prompt("en"))


class DomainsBlockTests(TestCase):
    def test_empty_domain_table_tells_the_model_to_return_null(self):
        from apps.resumes.services.resume_generation import _build_domains_block

        block = _build_domains_block()
        self.assertIn("none are configured", block)
        self.assertIn("do not invent one", block)

    def test_configured_domains_are_listed(self):
        from apps.domain.models import Domain
        from apps.resumes.services.resume_generation import _build_domains_block

        Domain.objects.create(name="Information Technology")
        self.assertIn("- Information Technology", _build_domains_block())

    def test_prompt_treats_a_stated_role_as_evidence_for_its_own_skill(self):
        # "Системный аналитик" losing System Analysis is what this guards.
        prompt = get_system_prompt("ru")
        collapsed = " ".join(prompt.split())
        self.assertIn("\"Системный аналитик\" is a mention of System Analysis", collapsed)
        self.assertIn("It says nothing about the other skills", collapsed)
