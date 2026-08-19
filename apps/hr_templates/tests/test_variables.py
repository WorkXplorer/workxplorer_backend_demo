from django.test import SimpleTestCase

from apps.hr_templates.constants import (
    VARIABLE_CANDIDATE_NAME,
    VARIABLE_POSITION,
    VARIABLE_COMPANY_NAME,
    ALL_VARIABLES,
    VARIABLE_LOCALIZATION,
    VARIABLE_INFO,
    extract_variables,
    normalize_variable,
    get_unknown_variables,
    get_used_variables,
    get_localized_form,
    render_invitation_text,
)


class VariableConstantsTests(SimpleTestCase):

    def test_all_variables_defined_in_localization(self):
        for var in ALL_VARIABLES:
            self.assertIn(var, VARIABLE_LOCALIZATION)

    def test_all_localization_keys_have_all_languages(self):
        expected_langs = {"en", "uz", "ru"}
        for var, translations in VARIABLE_LOCALIZATION.items():
            self.assertEqual(
                set(translations.keys()),
                expected_langs,
                f"{var} is missing some languages",
            )

    def test_variable_info_covers_all_variables(self):
        info_keys = {info["key"] for info in VARIABLE_INFO}
        self.assertEqual(info_keys, ALL_VARIABLES)

    def test_variable_info_has_descriptions(self):
        for info in VARIABLE_INFO:
            self.assertIn("key", info)
            self.assertIn("description", info)
            self.assertGreater(len(str(info["description"])), 0)

    def test_candidate_name_localized_forms(self):
        forms = VARIABLE_LOCALIZATION[VARIABLE_CANDIDATE_NAME]
        self.assertEqual(forms["en"], "{{candidate_name}}")
        self.assertEqual(forms["uz"], "{{nomzod_ismi}}")
        self.assertEqual(forms["ru"], "{{ИмяКандидата}}")

    def test_position_localized_forms(self):
        forms = VARIABLE_LOCALIZATION[VARIABLE_POSITION]
        self.assertEqual(forms["en"], "{{position}}")
        self.assertEqual(forms["uz"], "{{lavozim}}")
        self.assertEqual(forms["ru"], "{{Позиция}}")

    def test_company_name_localized_forms(self):
        forms = VARIABLE_LOCALIZATION[VARIABLE_COMPANY_NAME]
        self.assertEqual(forms["en"], "{{company_name}}")
        self.assertEqual(forms["uz"], "{{kompaniya_nomi}}")
        self.assertEqual(forms["ru"], "{{Компания}}")


class ExtractVariablesTests(SimpleTestCase):

    def test_extracts_single_variable(self):
        result = extract_variables("Hello {{candidate_name}}!")
        self.assertEqual(result, {"candidate_name"})

    def test_extracts_multiple_variables(self):
        result = extract_variables(
            "{{candidate_name}} applied for {{position}} at {{company_name}}"
        )
        self.assertEqual(result, {"candidate_name", "position", "company_name"})

    def test_extracts_duplicate_variables_once(self):
        result = extract_variables(
            "{{candidate_name}} is also {{candidate_name}}"
        )
        self.assertEqual(result, {"candidate_name"})

    def test_returns_empty_set_for_no_variables(self):
        result = extract_variables("Plain text without variables")
        self.assertEqual(result, set())

    def test_extracts_uzbek_variables(self):
        result = extract_variables("Salom {{nomzod_ismi}}!")
        self.assertEqual(result, {"nomzod_ismi"})

    def test_handles_empty_string(self):
        result = extract_variables("")
        self.assertEqual(result, set())


class NormalizeVariableTests(SimpleTestCase):

    def test_normalizes_english_name(self):
        self.assertEqual(normalize_variable("candidate_name"), VARIABLE_CANDIDATE_NAME)

    def test_normalizes_uzbek_name(self):
        self.assertEqual(normalize_variable("nomzod_ismi"), VARIABLE_CANDIDATE_NAME)

    def test_normalizes_russian_name(self):
        self.assertEqual(normalize_variable("имя_кандидата"), VARIABLE_CANDIDATE_NAME)

    def test_normalizes_case_insensitively(self):
        self.assertEqual(normalize_variable("Candidate_Name"), VARIABLE_CANDIDATE_NAME)

    def test_unknown_variable_returns_as_is(self):
        self.assertEqual(normalize_variable("unknown_var"), "unknown_var")

    def test_normalizes_all_position_forms(self):
        for raw in ("position", "lavozim", "должность"):
            self.assertEqual(normalize_variable(raw), VARIABLE_POSITION)

    def test_normalizes_all_company_forms(self):
        for raw in ("company_name", "kompaniya_nomi", "название_компании"):
            self.assertEqual(normalize_variable(raw), VARIABLE_COMPANY_NAME)

    def test_normalizes_new_russian_camelcase_forms(self):
        self.assertEqual(normalize_variable("ИмяКандидата"), VARIABLE_CANDIDATE_NAME)
        self.assertEqual(normalize_variable("Позиция"), VARIABLE_POSITION)
        self.assertEqual(normalize_variable("Компания"), VARIABLE_COMPANY_NAME)
        self.assertEqual(normalize_variable("Зарплата"), "salary")
        self.assertEqual(normalize_variable("ДатаНачала"), "start_date")
        self.assertEqual(normalize_variable("ИмяHR"), "hr_name")

    def test_legacy_russian_snake_case_still_resolves(self):
        # Backward compatibility: old saved templates must keep rendering.
        self.assertEqual(normalize_variable("имя_кандидата"), VARIABLE_CANDIDATE_NAME)
        self.assertEqual(normalize_variable("должность"), VARIABLE_POSITION)
        self.assertEqual(normalize_variable("название_компании"), VARIABLE_COMPANY_NAME)


class GetUnknownVariablesTests(SimpleTestCase):

    def test_no_unknown_variables(self):
        result = get_unknown_variables("Hello {{candidate_name}}!")
        self.assertEqual(result, set())

    def test_unknown_variables_detected(self):
        result = get_unknown_variables("Hello {{unknown_var}}!")
        self.assertEqual(result, {"unknown_var"})

    def test_mixed_known_and_unknown(self):
        result = get_unknown_variables(
            "{{candidate_name}} {{unknown_var}} {{another_one}}"
        )
        self.assertEqual(result, {"unknown_var", "another_one"})

    def test_localized_forms_not_unknown(self):
        result = get_unknown_variables("{{nomzod_ismi}} {{lavozim}} {{kompaniya_nomi}}")
        self.assertEqual(result, set())


class GetUsedVariablesTests(SimpleTestCase):

    def test_returns_used_variables(self):
        result = get_used_variables(
            "{{candidate_name}} works at {{company_name}}"
        )
        self.assertEqual(result, {VARIABLE_CANDIDATE_NAME, VARIABLE_COMPANY_NAME})

    def test_ignores_unknown_variables(self):
        result = get_used_variables(
            "{{candidate_name}} {{unknown_var}}"
        )
        self.assertEqual(result, {VARIABLE_CANDIDATE_NAME})

    def test_only_unknown_returns_empty(self):
        result = get_used_variables("{{unknown_var}}")
        self.assertEqual(result, set())


class GetLocalizedFormTests(SimpleTestCase):

    def test_returns_english_form_by_default(self):
        result = get_localized_form(VARIABLE_CANDIDATE_NAME)
        self.assertEqual(result, "{{candidate_name}}")

    def test_returns_uzbek_form(self):
        result = get_localized_form(VARIABLE_CANDIDATE_NAME, lang="uz")
        self.assertEqual(result, "{{nomzod_ismi}}")

    def test_returns_russian_form(self):
        result = get_localized_form(VARIABLE_CANDIDATE_NAME, lang="ru")
        self.assertEqual(result, "{{ИмяКандидата}}")

    def test_unknown_variable_falls_back(self):
        result = get_localized_form("unknown_var")
        self.assertEqual(result, "{{unknown_var}}")

    def test_unknown_language_falls_back_to_english(self):
        result = get_localized_form(VARIABLE_CANDIDATE_NAME, lang="fr")
        self.assertEqual(result, "{{candidate_name}}")


class FakeProfile:
    def __init__(self, full_name):
        self.full_name = full_name


class FakeCandidate:
    def __init__(self, full_name=None, email="test@example.com"):
        self.id = "test-id"
        self.candidateprofile = FakeProfile(full_name) if full_name else None
        self.email = email


class FakeVacancy:
    def __init__(self, title="Software Engineer"):
        self.title = title


class FakeCompany:
    def __init__(self, name="WorkXplorer"):
        self.name = name


class RenderInvitationTextTests(SimpleTestCase):

    def setUp(self):
        self.candidate = FakeCandidate(full_name="Diera Umarova", email="diera@example.com")
        self.vacancy = FakeVacancy(title="UX/UI Designer")
        self.company = FakeCompany(name="WorkXplorer")

    def test_renders_candidate_name_english(self):
        result = render_invitation_text(
            "Hello {{candidate_name}}!",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Hello Diera Umarova!")

    def test_renders_candidate_name_uzbek(self):
        result = render_invitation_text(
            "Salom {{nomzod_ismi}}!",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Salom Diera Umarova!")

    def test_renders_candidate_name_russian(self):
        result = render_invitation_text(
            "Здравствуйте, {{имя_кандидата}}!",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Здравствуйте, Diera Umarova!")

    def test_renders_position(self):
        result = render_invitation_text(
            "Position: {{position}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Position: UX/UI Designer")

    def test_renders_position_uzbek(self):
        result = render_invitation_text(
            "Lavozim: {{lavozim}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Lavozim: UX/UI Designer")

    def test_renders_position_russian(self):
        result = render_invitation_text(
            "Должность: {{должность}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Должность: UX/UI Designer")

    def test_renders_company_name(self):
        result = render_invitation_text(
            "Company: {{company_name}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Company: WorkXplorer")

    def test_renders_company_name_uzbek(self):
        result = render_invitation_text(
            "Kompaniya: {{kompaniya_nomi}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Kompaniya: WorkXplorer")

    def test_renders_all_variables_together(self):
        text = "{{candidate_name}}, {{position}}, {{company_name}}"
        result = render_invitation_text(text, self.candidate, self.vacancy, self.company)
        self.assertEqual(result, "Diera Umarova, UX/UI Designer, WorkXplorer")

    def test_renders_mixed_language_variables(self):
        text = "{{nomzod_ismi}} - {{position}} - {{название_компании}}"
        result = render_invitation_text(text, self.candidate, self.vacancy, self.company)
        self.assertEqual(result, "Diera Umarova - UX/UI Designer - WorkXplorer")

    def test_falls_back_to_email_when_no_full_name(self):
        candidate_no_profile = FakeCandidate(full_name=None, email="john@example.com")
        result = render_invitation_text(
            "Hello {{candidate_name}}!",
            candidate_no_profile, self.vacancy, self.company,
        )
        self.assertEqual(result, "Hello [Candidate Name Not Set]!")

    def test_handles_text_without_variables(self):
        result = render_invitation_text(
            "Plain text without variables",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Plain text without variables")

    def test_handles_empty_text(self):
        result = render_invitation_text("", self.candidate, self.vacancy, self.company)
        self.assertEqual(result, "")

    def test_keeps_unknown_variables_as_is(self):
        result = render_invitation_text(
            "{{candidate_name}} {{unknown_var}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Diera Umarova {{unknown_var}}")

    def test_renders_variables_with_spaces_inside_braces(self):
        result = render_invitation_text(
            "{{ candidate_name }} @ {{ position }}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Diera Umarova @ UX/UI Designer")

    def test_renders_variables_with_varying_whitespace(self):
        result = render_invitation_text(
            "{{candidate_name}} {{  position  }}   {{ company_name}}",
            self.candidate, self.vacancy, self.company,
        )
        self.assertEqual(result, "Diera Umarova UX/UI Designer   WorkXplorer")
