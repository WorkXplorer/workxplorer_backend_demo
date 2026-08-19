from itertools import count

from django.test import TestCase

from apps.applications.services.daily_report import _candidate_base
from apps.authentication.models import Candidate
from apps.profiles.models import CandidateProfile
from apps.resumes.models import Resume


class CandidateBaseTests(TestCase):
    """
    The standing candidate base: everyone registered and how far they got.

    A profile and a resume are separate optional steps, so a candidate can hold
    either, both or neither — which is the point of counting them apart.
    """

    def setUp(self):
        self._seq = count(1)

    def _candidate(self) -> Candidate:
        return Candidate.objects.create_user(
            email=f"candidate{next(self._seq)}-{id(self)}@example.com",
            password="testpass123",
        )

    def _profile(self, candidate) -> CandidateProfile:
        return CandidateProfile.objects.create(
            candidate=candidate, full_name="Test Candidate"
        )

    def _resume(self, candidate) -> Resume:
        return Resume.objects.create(candidate=candidate, description="A resume")

    def test_counts_everyone_registered(self):
        for _ in range(3):
            self._candidate()

        self.assertEqual(_candidate_base()["all_time"], 3)

    def test_profiles_and_resumes_are_counted_separately(self):
        both = self._candidate()
        self._profile(both)
        self._resume(both)

        profile_only = self._candidate()
        self._profile(profile_only)

        resume_only = self._candidate()
        self._resume(resume_only)

        self._candidate()  # neither

        base = _candidate_base()

        self.assertEqual(base["all_time"], 4)
        self.assertEqual(base["with_profile"], 2)
        self.assertEqual(base["with_resume"], 2)

    def test_several_resumes_do_not_inflate_any_count(self):
        """
        ``resumes`` is a reverse FK, so the join multiplies rows.

        Without distinct=True a candidate with three resumes would be counted
        three times in every column of the aggregate, not just its own.
        """
        candidate = self._candidate()
        self._profile(candidate)
        for _ in range(3):
            self._resume(candidate)

        base = _candidate_base()

        self.assertEqual(base["all_time"], 1)
        self.assertEqual(base["with_profile"], 1)
        self.assertEqual(base["with_resume"], 1)

    def test_an_empty_platform_reports_zeroes_rather_than_none(self):
        self.assertEqual(
            _candidate_base(),
            {"all_time": 0, "with_profile": 0, "with_resume": 0, "ever_applied": 0},
        )
