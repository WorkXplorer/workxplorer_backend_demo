from types import SimpleNamespace

from django.test import TestCase, override_settings

from apps.authentication.transitions import (
    VACANCY_APPLY,
    CREATE_PROFILE,
    REGISTRATION,
    CREATE_RESUME,
    VERIFY_VAULT,
    get_candidate_progress,
    get_safe_progress,
    get_step_url,
    resolve_candidate_status,
    update_candidate_step,
)


def _make_candidate(progress=None):
    """Create a lightweight stand-in with the fields transitions.py reads."""
    ns = SimpleNamespace(onboarding_progress=progress if progress is not None else {})
    return ns


class GetSafeProgressTests(TestCase):
    def test_returns_dict_when_valid(self):
        c = _make_candidate({CREATE_PROFILE: "2026-01-01T00:00:00"})
        self.assertEqual(get_safe_progress(c), {CREATE_PROFILE: "2026-01-01T00:00:00"})

    def test_returns_empty_dict_for_none(self):
        c = _make_candidate(None)
        self.assertEqual(get_safe_progress(c), {})

    def test_returns_empty_dict_for_list(self):
        c = _make_candidate(["bad", "data"])
        self.assertEqual(get_safe_progress(c), {})

    def test_returns_empty_dict_for_string(self):
        c = _make_candidate("corrupted")
        self.assertEqual(get_safe_progress(c), {})


class ResolveCandidateStatusTests(TestCase):
    def test_empty_progress_returns_registered(self):
        c = _make_candidate({})
        self.assertEqual(resolve_candidate_status(c), REGISTRATION)

    def test_none_progress_returns_registered(self):
        c = _make_candidate(None)
        self.assertEqual(resolve_candidate_status(c), REGISTRATION)

    def test_single_step_completed(self):
        c = _make_candidate({CREATE_PROFILE: "2026-01-01T00:00:00"})
        self.assertEqual(resolve_candidate_status(c), CREATE_PROFILE)

    def test_highest_ordered_step_wins(self):
        """Status should be the highest step in flow order, not the latest timestamp."""
        c = _make_candidate({
            CREATE_PROFILE: "2026-04-16T12:00:00",
            CREATE_RESUME: "2026-04-16T11:00:00",
            VACANCY_APPLY: "2026-04-16T10:00:00",
        })
        # VACANCY_APPLY is the highest in flow order, even though its timestamp is earliest
        self.assertEqual(resolve_candidate_status(c), VACANCY_APPLY)

    def test_all_steps_returns_vault_verified(self):
        c = _make_candidate({
            CREATE_PROFILE: "2026-01-01T00:00:00",
            CREATE_RESUME: "2026-01-02T00:00:00",
            VACANCY_APPLY: "2026-01-03T00:00:00",
            VERIFY_VAULT: "2026-01-04T00:00:00",
        })
        self.assertEqual(resolve_candidate_status(c), VERIFY_VAULT)

    def test_unknown_keys_ignored(self):
        c = _make_candidate({"unknown_step": "2026-01-01T00:00:00"})
        self.assertEqual(resolve_candidate_status(c), REGISTRATION)


class UpdateCandidateStepTests(TestCase):
    def test_adds_new_step(self):
        saved = {}

        class FakeCandidate:
            onboarding_progress = {}
            def save(self, update_fields=None):
                saved["progress"] = self.onboarding_progress
                saved["fields"] = update_fields

        c = FakeCandidate()
        update_candidate_step(c, CREATE_PROFILE)

        self.assertIn(CREATE_PROFILE, saved["progress"])
        self.assertEqual(saved["fields"], ["onboarding_progress"])

    def test_idempotent_does_not_overwrite(self):
        original_ts = "2026-01-01T00:00:00"

        class FakeCandidate:
            onboarding_progress = {CREATE_PROFILE: original_ts}
            def save(self, update_fields=None):
                pass

        c = FakeCandidate()
        update_candidate_step(c, CREATE_PROFILE)
        self.assertEqual(c.onboarding_progress[CREATE_PROFILE], original_ts)


@override_settings(FRONTEND_URL="https://app.workxplorer.uz")
class GetStepUrlTests(TestCase):
    def test_builds_url_with_language(self):
        url = get_step_url(CREATE_PROFILE, "ru")
        self.assertEqual(url, "https://app.workxplorer.uz/ru/dashboard/profile")

    def test_defaults_to_english(self):
        url = get_step_url(CREATE_RESUME)
        self.assertEqual(url, "https://app.workxplorer.uz/en/dashboard/resume/create")

    def test_unknown_step_returns_empty(self):
        url = get_step_url("nonexistent_step", "en")
        self.assertEqual(url, "")

    @override_settings(FRONTEND_URL="")
    def test_empty_frontend_url_returns_empty(self):
        url = get_step_url(CREATE_PROFILE, "en")
        self.assertEqual(url, "")

    def test_trailing_slash_stripped(self):
        with self.settings(FRONTEND_URL="https://app.workxplorer.uz/"):
            url = get_step_url(VACANCY_APPLY, "uz")
            self.assertEqual(url, "https://app.workxplorer.uz/uz/dashboard/vacancies/list")


@override_settings(FRONTEND_URL="https://app.workxplorer.uz")
class GetCandidateProgressTests(TestCase):
    def test_empty_progress(self):
        c = _make_candidate({})
        result = get_candidate_progress(c, language="en")

        self.assertEqual(result["progress"], 0)
        self.assertEqual(result["status"], REGISTRATION)
        self.assertEqual(result["current_step"], CREATE_PROFILE)
        self.assertEqual(len(result["steps"]), 4)
        self.assertFalse(any(s["completed"] for s in result["steps"]))

    def test_partial_progress(self):
        c = _make_candidate({
            CREATE_PROFILE: "2026-04-16T10:00:00",
            CREATE_RESUME: "2026-04-16T11:00:00",
        })
        result = get_candidate_progress(c, language="en")

        self.assertEqual(result["progress"], 50)
        self.assertEqual(result["status"], CREATE_RESUME)
        self.assertEqual(result["current_step"], VACANCY_APPLY)

    def test_full_progress(self):
        c = _make_candidate({
            CREATE_PROFILE: "2026-01-01T00:00:00",
            CREATE_RESUME: "2026-01-02T00:00:00",
            VACANCY_APPLY: "2026-01-03T00:00:00",
            VERIFY_VAULT: "2026-01-04T00:00:00",
        })
        result = get_candidate_progress(c, language="en")

        self.assertEqual(result["progress"], 100)
        self.assertEqual(result["status"], VERIFY_VAULT)
        self.assertIsNone(result["current_step"])
        self.assertTrue(all(s["completed"] for s in result["steps"]))

    def test_steps_include_urls(self):
        c = _make_candidate({})
        result = get_candidate_progress(c, language="ru")

        for step in result["steps"]:
            self.assertIn("url", step)
            self.assertTrue(step["url"].startswith("https://app.workxplorer.uz/ru/"))

    def test_steps_include_completed_at(self):
        ts = "2026-04-16T10:00:00"
        c = _make_candidate({CREATE_PROFILE: ts})
        result = get_candidate_progress(c, language="en")

        profile_step = next(s for s in result["steps"] if s["code"] == CREATE_PROFILE)
        self.assertEqual(profile_step["completed_at"], ts)

        resume_step = next(s for s in result["steps"] if s["code"] == CREATE_RESUME)
        self.assertIsNone(resume_step["completed_at"])
