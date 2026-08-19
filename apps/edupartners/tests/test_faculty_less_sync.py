import uuid

from django.test import TestCase

from apps.edupartners.models import EduPartner, EduPartnersType, Faculty
from apps.authentication.models import Candidate
from apps.edupartners.services.analytics import EduPartnerAnalyticsService


class FacultyLessEdupartnerSyncTestCase(TestCase):
    """
    Edupartners with candidates but zero active faculties were previously
    invisible to the analytics sync task: get_faculty_ids() only looks at
    Faculty rows, so such edupartners never got a job enqueued at all.
    """

    @classmethod
    def setUpTestData(cls):
        cls.edupartner_type = EduPartnersType.objects.create(name="University")

        # Mirrors UTAS: candidates directly on the edupartner, no faculty at all.
        cls.faculty_less = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Faculty-less University",
            edupartner_type=cls.edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
            is_active=True,
        )
        Candidate.objects.create(
            email="student1@faculty-less.test",
            edupartner=cls.faculty_less,
            faculty=None,
        )
        Candidate.objects.create(
            email="student2@faculty-less.test",
            edupartner=cls.faculty_less,
            faculty=None,
        )

        # Mirrors TMII: has both a faculty and candidates -- already synced
        # via the existing per-faculty path, must NOT show up as faculty-less.
        cls.with_faculty = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Normal University",
            edupartner_type=cls.edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
            is_active=True,
        )
        cls.faculty = Faculty.objects.create(
            name="Computer Science",
            edupartner=cls.with_faculty,
            is_active=True,
        )
        Candidate.objects.create(
            email="student3@with-faculty.test",
            edupartner=cls.with_faculty,
            faculty=cls.faculty,
        )

        # Edupartner with zero candidates: nothing to sync, must not appear either.
        cls.empty = EduPartner.objects.create(
            id=uuid.uuid4(),
            name="Empty University",
            edupartner_type=cls.edupartner_type,
            country="Uzbekistan",
            city="Tashkent",
            is_active=True,
        )

    def test_faculty_less_edupartner_with_candidates_is_returned(self):
        ids = EduPartnerAnalyticsService.get_faculty_less_edupartner_ids()
        self.assertIn(self.faculty_less.id, ids)

    def test_edupartner_with_faculty_is_excluded(self):
        ids = EduPartnerAnalyticsService.get_faculty_less_edupartner_ids()
        self.assertNotIn(self.with_faculty.id, ids)

    def test_edupartner_with_no_candidates_is_excluded(self):
        ids = EduPartnerAnalyticsService.get_faculty_less_edupartner_ids()
        self.assertNotIn(self.empty.id, ids)

    def test_get_edupartner_analytics_works_for_faculty_less_edupartner(self):
        result = EduPartnerAnalyticsService.get_edupartner_analytics(self.faculty_less.id)
        self.assertIsNotNone(result)
        self.assertEqual(result["statistics"]["source_students"], 2)
        self.assertNotIn("faculty", result)
