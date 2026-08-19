from datetime import date, datetime, time, timedelta
from itertools import count
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.applications.models.applications import JobApplication
from apps.applications.models.choices import ApplicationStatus
from apps.applications.services.daily_report import (
    build_daily_application_report,
    send_daily_application_report,
)
from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.vacancies.models import Vacancy


class DailyApplicationReportTests(TestCase):
    """Cover the date windows and per-company grouping of the daily report."""

    @classmethod
    def setUpTestData(cls):
        cls.company_a = Company.objects.create(name="Company A", tin="100000001")
        cls.company_b = Company.objects.create(name="Company B", tin="100000002")

        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company_a,
        )
        cls.vacancy_a = Vacancy.objects.create(
            title="Vacancy A", company=cls.company_a, created_by=cls.recruiter
        )
        cls.vacancy_b = Vacancy.objects.create(
            title="Vacancy B", company=cls.company_b, created_by=cls.recruiter
        )
        cls.report_date = timezone.localdate() - timedelta(days=1)

    def setUp(self):
        # A candidate may only apply once per vacancy, so every application in
        # these tests needs its own candidate.
        self._candidate_seq = count(1)

    def _local(self, day: date, hour: int = 12) -> datetime:
        return timezone.make_aware(
            datetime.combine(day, time(hour=hour)), timezone.get_current_timezone()
        )

    def _apply(self, vacancy, days_ago: int, **kwargs) -> JobApplication:
        """Create an application backdated ``days_ago`` local days from today."""
        index = next(self._candidate_seq)
        candidate = Candidate.objects.create_user(
            email=f"candidate{index}-{id(self)}@example.com",
            password="testpass123",
        )
        return JobApplication.objects.create(
            candidate=candidate,
            vacancy=vacancy,
            applied_at=self._local(timezone.localdate() - timedelta(days=days_ago)),
            **kwargs,
        )

    def test_day_window_counts_only_the_report_date(self):
        self._apply(self.vacancy_a, days_ago=1)
        self._apply(self.vacancy_a, days_ago=1)
        self._apply(self.vacancy_a, days_ago=2)
        self._apply(self.vacancy_a, days_ago=0)  # today, after the report window

        report = build_daily_application_report(report_date=self.report_date)

        self.assertEqual(report["totals"]["day"], 2)
        self.assertEqual(report["totals"]["prev_day"], 1)
        self.assertEqual(report["totals"]["all_time"], 4)

    def test_companies_are_grouped_and_ranked_by_day_count(self):
        self._apply(self.vacancy_a, days_ago=1)
        self._apply(self.vacancy_a, days_ago=1)
        self._apply(self.vacancy_b, days_ago=1)
        self._apply(self.vacancy_b, days_ago=30)  # counts toward all-time only

        report = build_daily_application_report(report_date=self.report_date)

        names = [c["name"] for c in report["companies"]]
        self.assertEqual(names, ["Company A", "Company B"])
        self.assertEqual(report["companies"][0]["day"], 2)
        self.assertEqual(report["companies"][1]["day"], 1)
        self.assertEqual(report["companies"][1]["all_time"], 2)
        self.assertEqual(report["companies_active"], 2)
        self.assertEqual(report["companies_hidden"], 0)

    def test_companies_beyond_the_limit_are_folded_into_a_remainder(self):
        self._apply(self.vacancy_a, days_ago=1)
        self._apply(self.vacancy_b, days_ago=1)

        report = build_daily_application_report(
            report_date=self.report_date, top_companies=1
        )

        self.assertEqual(len(report["companies"]), 1)
        self.assertEqual(report["companies_hidden"], 1)
        self.assertEqual(report["companies_hidden_day"], 1)

    def test_week_window_starts_on_the_report_date_monday(self):
        report = build_daily_application_report(report_date=self.report_date)

        week_start = date.fromisoformat(report["week_start"])
        self.assertEqual(week_start.weekday(), 0)
        self.assertLessEqual(week_start, self.report_date)
        self.assertLess((self.report_date - week_start).days, 7)

    def test_statuses_group_legacy_status_values_into_categories(self):
        self._apply(self.vacancy_a, days_ago=1, status=ApplicationStatus.AI_FAILED)
        self._apply(self.vacancy_a, days_ago=1, status=ApplicationStatus.APPLIED)
        # Both legacy interview statuses fold into the INTERVIEWING category.
        self._apply(self.vacancy_a, days_ago=1, status=ApplicationStatus.INTERVIEW_SCHEDULED)
        self._apply(self.vacancy_a, days_ago=1, status=ApplicationStatus.INTERVIEWED)
        self._apply(self.vacancy_a, days_ago=40, status=ApplicationStatus.REJECTED)

        report = build_daily_application_report(report_date=self.report_date)

        self.assertEqual(
            report["statuses"]["day"],
            {"AI_FAILED": 1, "APPLIED": 1, "INTERVIEWING": 2},
        )
        self.assertEqual(report["statuses"]["all_time"]["REJECTED"], 1)

    def test_day_status_counts_sum_to_the_day_total(self):
        self._apply(self.vacancy_a, days_ago=1, status=ApplicationStatus.AI_FAILED)
        self._apply(self.vacancy_a, days_ago=1)
        self._apply(self.vacancy_b, days_ago=1)
        self._apply(self.vacancy_b, days_ago=3)

        report = build_daily_application_report(report_date=self.report_date)

        self.assertEqual(sum(report["statuses"]["day"].values()), report["totals"]["day"])
        self.assertEqual(
            sum(report["statuses"]["all_time"].values()), report["totals"]["all_time"]
        )

    def test_unmapped_status_keys_land_in_the_other_bucket(self):
        application = self._apply(self.vacancy_a, days_ago=1)
        # Bypass save() validation to simulate a status key with no matching
        # ApplicationStatusModel row for the company.
        JobApplication.objects.filter(pk=application.pk).update(status="MYSTERY_KEY")

        report = build_daily_application_report(report_date=self.report_date)

        self.assertEqual(report["statuses"]["day"].get("OTHER"), 1)

    def test_signups_are_grouped_by_university(self):
        from apps.edupartners.models import EduPartner, EduPartnersType

        partner_type = EduPartnersType.objects.create(name="University")
        tuit = EduPartner.objects.create(
            name="TUIT", edupartner_type=partner_type, country="UZ", city="Tashkent"
        )
        wiut = EduPartner.objects.create(
            name="Westminster", edupartner_type=partner_type, country="UZ", city="Tashkent"
        )

        joined = self._local(self.report_date, hour=9)
        for index, partner in enumerate([tuit, tuit, wiut, None]):
            candidate = Candidate.objects.create_user(
                email=f"signup{index}@example.com", password="testpass123"
            )
            candidate.edupartner = partner
            candidate.date_joined = joined
            candidate.save(update_fields=["edupartner", "date_joined"])

        report = build_daily_application_report(report_date=self.report_date)
        signups = report["signups"]

        self.assertEqual(signups["totals"]["day"], 4)
        self.assertEqual(
            [(u["name"], u["day"]) for u in signups["universities"]],
            [("TUIT", 2), ("Westminster", 1)],
        )
        # Candidates without a university are their own line, not ranked among
        # the named ones, so the parts still add up to the headline.
        self.assertEqual(signups["no_university"]["day"], 1)
        self.assertEqual(
            sum(u["day"] for u in signups["universities"])
            + signups["no_university"]["day"],
            signups["totals"]["day"],
        )

    def test_signup_list_is_capped_with_a_remainder(self):
        from apps.edupartners.models import EduPartner, EduPartnersType

        partner_type = EduPartnersType.objects.create(name="University")
        joined = self._local(self.report_date, hour=9)
        for index in range(3):
            partner = EduPartner.objects.create(
                name=f"Uni {index}",
                edupartner_type=partner_type,
                country="UZ",
                city="Tashkent",
            )
            candidate = Candidate.objects.create_user(
                email=f"capped{index}@example.com", password="testpass123"
            )
            candidate.edupartner = partner
            candidate.date_joined = joined
            candidate.save(update_fields=["edupartner", "date_joined"])

        with self.settings(DAILY_APPLICATION_REPORT_TOP_UNIVERSITIES=1):
            report = build_daily_application_report(report_date=self.report_date)

        signups = report["signups"]
        self.assertEqual(len(signups["universities"]), 1)
        self.assertEqual(signups["universities_hidden"], 2)
        self.assertEqual(signups["universities_hidden_day"], 2)

    @patch("apps.applications.services.daily_report.requests.post")
    def test_report_is_skipped_when_the_bot_secret_is_missing(self, mock_post):
        with self.settings(TELEGRAM_BOT_API_SECRET=""):
            delivered = send_daily_application_report({"report_date": "2026-01-01"})

        self.assertFalse(delivered)
        mock_post.assert_not_called()


class DailyReportMetricsTests(TestCase):
    """
    Cover the sections added beyond the per-company counts: the funnel, who is
    behind the applications, and the marketplace.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Metrics Co", tin="200000001")
        cls.recruiter = Recruiter.objects.create_user(
            email="metrics-recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        cls.vacancy = Vacancy.objects.create(
            title="Vacancy M", company=cls.company, created_by=cls.recruiter
        )
        cls.other_vacancy = Vacancy.objects.create(
            title="Vacancy N", company=cls.company, created_by=cls.recruiter
        )
        cls.report_date = timezone.localdate() - timedelta(days=1)

    def setUp(self):
        self._candidate_seq = count(1)

    def _local(self, day: date, hour: int = 12) -> datetime:
        return timezone.make_aware(
            datetime.combine(day, time(hour=hour)), timezone.get_current_timezone()
        )

    def _candidate(self) -> Candidate:
        index = next(self._candidate_seq)
        return Candidate.objects.create_user(
            email=f"metrics{index}-{id(self)}@example.com", password="testpass123"
        )

    def _apply(self, vacancy=None, days_ago: int = 1, candidate=None, **kwargs):
        return JobApplication.objects.create(
            candidate=candidate or self._candidate(),
            vacancy=vacancy or self.vacancy,
            applied_at=self._local(timezone.localdate() - timedelta(days=days_ago)),
            **kwargs,
        )

    def _report(self):
        return build_daily_application_report(report_date=self.report_date)

    def test_vacancies_are_ranked_by_the_day_count(self):
        self._apply(self.vacancy)
        self._apply(self.vacancy)
        self._apply(self.other_vacancy)
        self._apply(self.other_vacancy, days_ago=5)  # all time only

        report = self._report()

        self.assertEqual(
            [(row["title"], row["day"]) for row in report["vacancies"]],
            [("Vacancy M", 2), ("Vacancy N", 1)],
        )
        self.assertEqual(report["vacancies"][1]["all_time"], 2)
        self.assertEqual(report["vacancies_active"], 2)

    def test_vacancies_beyond_the_limit_are_folded_into_a_remainder(self):
        self._apply(self.vacancy)
        self._apply(self.other_vacancy)

        with self.settings(DAILY_APPLICATION_REPORT_TOP_VACANCIES=1):
            report = self._report()

        self.assertEqual(len(report["vacancies"]), 1)
        self.assertEqual(report["vacancies_hidden"], 1)
        self.assertEqual(report["vacancies_hidden_day"], 1)

    def test_funnel_counts_progress_from_timestamps_not_current_status(self):
        reviewed = self._apply()
        reviewed.in_review_at = self._local(self.report_date, hour=15)
        reviewed.save(update_fields=["in_review_at"], skip_full_clean=True)

        hired = self._apply(days_ago=8)
        hired.in_review_at = self._local(self.report_date - timedelta(days=7))
        hired.hired_at = self._local(self.report_date - timedelta(days=3))
        hired.save(update_fields=["in_review_at", "hired_at"], skip_full_clean=True)

        self._apply()

        funnel = self._report()["funnel"]

        self.assertEqual(funnel["applied"], 3)
        self.assertEqual(funnel["reviewed"], 2)
        self.assertEqual(funnel["hired"], 1)
        # Applied 8 days before today, hired 3 days before the report date.
        self.assertEqual(funnel["days_to_hire"], 4.0)

    def test_funnel_counts_vacancy_views(self):
        from apps.vacancies.models import VacancyView

        VacancyView.objects.create(vacancy=self.vacancy, candidate=self._candidate())
        VacancyView.objects.create(vacancy=self.vacancy, candidate=self._candidate())

        self.assertEqual(self._report()["funnel"]["views"], 2)

    def test_applicants_separate_people_from_applications(self):
        repeat = self._candidate()
        self._apply(self.vacancy, candidate=repeat)
        self._apply(self.other_vacancy, candidate=repeat)
        self._apply()

        # Applied before the report date, so not a first-time applicant on it.
        returning = self._candidate()
        self._apply(self.vacancy, days_ago=10, candidate=returning)
        self._apply(self.other_vacancy, days_ago=1, candidate=returning)

        applicants = self._report()["applicants"]

        self.assertEqual(applicants["candidates"], 3)
        self.assertEqual(applicants["first_time"], 2)

    def test_marketplace_reports_idle_and_saved_vacancies(self):
        from apps.vacancies.models import FavouriteVacancy

        # Old enough to be judged idle, and never applied to.
        Vacancy.objects.filter(pk=self.other_vacancy.pk).update(
            created_at=self._local(self.report_date - timedelta(days=30))
        )
        Vacancy.objects.filter(pk=self.vacancy.pk).update(
            created_at=self._local(self.report_date - timedelta(days=30))
        )
        self._apply(self.vacancy)

        saved_only = self._candidate()
        FavouriteVacancy.objects.create(
            candidate=saved_only, vacancy=self.other_vacancy
        )
        applied_too = self._apply(self.vacancy)
        FavouriteVacancy.objects.create(
            candidate=applied_too.candidate, vacancy=self.vacancy
        )

        marketplace = self._report()["marketplace"]

        self.assertEqual(marketplace["open_vacancies"], 2)
        self.assertEqual(marketplace["idle_vacancies"], 1)
        self.assertEqual(marketplace["idle_after_days"], 7)
        # Only the bookmark that never turned into an application counts.
        self.assertEqual(marketplace["saved_not_applied"], 1)

    def test_week_average_divides_by_the_days_covered(self):
        report = self._report()

        week_days = report["totals"]["week_days"]
        self.assertEqual(week_days, self.report_date.weekday() + 1)
        self.assertEqual(
            report["totals"]["week_avg_day"],
            round(report["totals"]["week"] / week_days, 1),
        )


class DailyReportEducationTests(TestCase):
    """Cover the university report's own numbers, separate from the signups."""

    @classmethod
    def setUpTestData(cls):
        from apps.edupartners.models import EduPartner, EduPartnersType

        cls.company = Company.objects.create(name="Edu Co", tin="300000001")
        cls.recruiter = Recruiter.objects.create_user(
            email="edu-recruiter@example.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        cls.vacancy = Vacancy.objects.create(
            title="Vacancy E", company=cls.company, created_by=cls.recruiter
        )
        partner_type = EduPartnersType.objects.create(name="University")
        cls.tuit = EduPartner.objects.create(
            name="TUIT", edupartner_type=partner_type, country="UZ", city="Tashkent"
        )
        cls.wiut = EduPartner.objects.create(
            name="Westminster",
            edupartner_type=partner_type,
            country="UZ",
            city="Tashkent",
        )
        cls.report_date = timezone.localdate() - timedelta(days=1)

    def setUp(self):
        self._candidate_seq = count(1)

    def _local(self, day: date, hour: int = 12) -> datetime:
        return timezone.make_aware(
            datetime.combine(day, time(hour=hour)), timezone.get_current_timezone()
        )

    def _candidate(self, partner=None, joined_days_ago: int = 1) -> Candidate:
        index = next(self._candidate_seq)
        candidate = Candidate.objects.create_user(
            email=f"edu{index}-{id(self)}@example.com", password="testpass123"
        )
        candidate.edupartner = partner
        candidate.date_joined = self._local(
            timezone.localdate() - timedelta(days=joined_days_ago)
        )
        candidate.save(update_fields=["edupartner", "date_joined"])
        return candidate

    def _apply(self, candidate, vacancy=None, days_ago: int = 1):
        return JobApplication.objects.create(
            candidate=candidate,
            vacancy=vacancy or self.vacancy,
            applied_at=self._local(timezone.localdate() - timedelta(days=days_ago)),
        )

    def test_applications_are_grouped_by_the_candidate_university(self):
        self._apply(self._candidate(self.tuit))
        self._apply(self._candidate(self.tuit))
        self._apply(self._candidate(self.wiut))
        self._apply(self._candidate(None))

        education = build_daily_application_report(report_date=self.report_date)[
            "education"
        ]

        self.assertEqual(
            [(row["name"], row["day"]) for row in education["universities"]],
            [("TUIT", 2), ("Westminster", 1)],
        )
        # Applications from candidates with no university are their own bucket,
        # so the parts still add up to the day's total.
        self.assertEqual(education["no_university"]["day"], 1)

    def test_registered_candidates_who_never_applied_are_counted(self):
        self._apply(self._candidate(self.tuit))
        self._candidate(self.tuit)
        self._candidate(None)

        education = build_daily_application_report(report_date=self.report_date)[
            "education"
        ]

        self.assertEqual(education["never_applied"], 2)

    def test_resume_completion_covers_the_days_new_users(self):
        from apps.resumes.models import Resume

        with_resume = self._candidate(self.tuit)
        Resume.objects.create(candidate=with_resume, description="A resume")
        self._candidate(self.tuit)
        # Joined earlier, so outside the day the report is about.
        self._candidate(self.tuit, joined_days_ago=9)

        education = build_daily_application_report(report_date=self.report_date)[
            "education"
        ]

        self.assertEqual(education["resumes"], {"new_users": 2, "with_resume": 1})

    def test_career_roadmaps_are_counted(self):
        from apps.resumes.models import Resume
        from apps.student_analytics.models import SkillRoadmap, StudentAnalytics

        for role in ("Frontend Developer", "Frontend Developer", "Data Analyst"):
            candidate = self._candidate(self.tuit)
            resume = Resume.objects.create(candidate=candidate, description="A resume")
            analytics = StudentAnalytics.objects.create(
                candidate=candidate, resume=resume, target_role=role
            )
            SkillRoadmap.objects.create(analytics=analytics, target_role=role)

        roadmaps = build_daily_application_report(report_date=self.report_date)[
            "roadmaps"
        ]

        self.assertEqual(roadmaps["all_time"], 3)
        self.assertEqual(roadmaps["day"], 0)


class DailyReportChurnTests(TestCase):
    """
    Cover the churn block and the recent-recruiter list.

    Both are read off ``last_login``, which has no history behind it, so these
    tests pin the two decisions that follow from that: the rate counts only
    users who have signed in at least once, and the window is measured from the
    end of the report day rather than from the moment the test runs.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Churn Co", tin="300000001")
        cls.report_date = timezone.localdate() - timedelta(days=1)

    def setUp(self):
        self._user_seq = count(1)

    def _ago(self, days) -> datetime:
        return timezone.now() - timedelta(days=days)

    def _candidate(self, last_login=None, **kwargs) -> Candidate:
        index = next(self._user_seq)
        return Candidate.objects.create_user(
            email=f"churn-cand{index}-{id(self)}@example.com",
            password="testpass123",
            last_login=last_login,
            **kwargs,
        )

    def _recruiter(self, last_login=None, full_name=None, **kwargs) -> Recruiter:
        from apps.profiles.models import RecruiterProfile

        index = next(self._user_seq)
        recruiter = Recruiter.objects.create_user(
            email=f"churn-rec{index}-{id(self)}@example.com",
            password="testpass123",
            is_recruiter=True,
            company=self.company,
            last_login=last_login,
            **kwargs,
        )
        if full_name:
            RecruiterProfile.objects.create(recruiter=recruiter, full_name=full_name)
        return recruiter

    def _report(self):
        return build_daily_application_report(report_date=self.report_date)

    def test_churn_counts_users_who_have_not_signed_in_for_the_window(self):
        self._candidate(last_login=self._ago(2))
        self._candidate(last_login=self._ago(29))
        self._candidate(last_login=self._ago(45))
        self._candidate(last_login=self._ago(400))

        churn = self._report()["churn"]["candidates"]

        self.assertEqual(churn["known"], 4)
        self.assertEqual(churn["active"], 2)
        self.assertEqual(churn["churned"], 2)
        self.assertEqual(churn["rate"], 50.0)

    def test_users_who_never_signed_in_are_reported_apart_from_the_rate(self):
        # Registering and never coming back is a signup problem, not churn;
        # folding the two together would report one as the other.
        self._candidate(last_login=self._ago(2))
        self._candidate(last_login=None)
        self._candidate(last_login=None)

        churn = self._report()["churn"]["candidates"]

        self.assertEqual(churn["known"], 1)
        self.assertEqual(churn["churned"], 0)
        self.assertEqual(churn["rate"], 0.0)
        self.assertEqual(churn["never_logged_in"], 2)

    def test_churn_rate_is_none_rather_than_zero_when_nobody_signed_in(self):
        self._candidate(last_login=None)

        churn = self._report()["churn"]["candidates"]

        self.assertIsNone(churn["rate"])

    def test_deactivated_accounts_are_left_out_of_churn(self):
        self._candidate(last_login=self._ago(2))
        self._candidate(last_login=self._ago(90), is_active=False)

        churn = self._report()["churn"]["candidates"]

        self.assertEqual(churn["known"], 1)
        self.assertEqual(churn["churned"], 0)

    def test_candidates_and_recruiters_are_counted_separately(self):
        self._candidate(last_login=self._ago(90))
        self._recruiter(last_login=self._ago(1))

        churn = self._report()["churn"]

        self.assertEqual(churn["window_days"], 30)
        self.assertEqual(churn["candidates"]["churned"], 1)
        self.assertEqual(churn["recruiters"]["churned"], 0)
        self.assertEqual(churn["recruiters"]["active"], 1)

    def test_recruiters_are_listed_most_recent_sign_in_first(self):
        self._recruiter(last_login=self._ago(10), full_name="Old Timer")
        self._recruiter(last_login=self._ago(1), full_name="Yesterday")
        self._recruiter(last_login=self._ago(4), full_name="Midweek")
        self._recruiter(last_login=None, full_name="Never")

        recruiters = self._report()["recruiters"]

        self.assertEqual(
            [row["name"] for row in recruiters["recent"]],
            ["Yesterday", "Midweek", "Old Timer"],
        )
        self.assertEqual(recruiters["recent"][0]["company"], "Churn Co")
        self.assertEqual(recruiters["total"], 4)

    def test_recruiter_list_stops_at_five(self):
        for days in range(8):
            self._recruiter(last_login=self._ago(days + 1), full_name=f"R{days}")

        recruiters = self._report()["recruiters"]

        self.assertEqual(len(recruiters["recent"]), 5)
        self.assertEqual(recruiters["recent"][0]["name"], "R0")

    def test_a_recruiter_with_several_profiles_appears_once(self):
        from apps.profiles.models import RecruiterProfile

        recruiter = self._recruiter(last_login=self._ago(1), full_name="First Profile")
        RecruiterProfile.objects.create(recruiter=recruiter, full_name="Second Profile")

        recent = self._report()["recruiters"]["recent"]

        self.assertEqual(len(recent), 1)
        self.assertIn(recent[0]["name"], {"First Profile", "Second Profile"})

    def test_a_recruiter_without_a_profile_still_gets_a_row(self):
        self._recruiter(last_login=self._ago(1))

        recent = self._report()["recruiters"]["recent"]

        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["name"], "—")

    def test_days_ago_is_measured_from_the_end_of_the_report_day(self):
        # The report covers yesterday, so a sign-in from today happened after
        # its window closed and is clamped rather than reported as negative.
        self._recruiter(last_login=self._ago(0), full_name="Today")

        recent = self._report()["recruiters"]["recent"]

        self.assertEqual(recent[0]["days_ago"], 0)

    def test_the_whole_payload_survives_a_json_round_trip(self):
        # The management command dumps the payload to JSON and the sender POSTs
        # it, so a datetime or a UUID reaching the payload breaks delivery
        # rather than looking wrong — and the recruiter rows carry both.
        import json

        self._recruiter(last_login=self._ago(1), full_name="Recent")
        self._candidate(last_login=self._ago(90))

        payload = self._report()

        restored = json.loads(json.dumps(payload))
        self.assertEqual(restored["churn"]["candidates"]["churned"], 1)
        self.assertIsInstance(restored["recruiters"]["recent"][0]["last_login"], str)


class DailyReportMobileUsersTests(TestCase):
    """Cover the unique mobile app user counts in the report."""

    @classmethod
    def setUpTestData(cls):
        cls.report_date = timezone.localdate() - timedelta(days=1)

    def setUp(self):
        self._user_seq = count(1)

    def _ago(self, days) -> datetime:
        return timezone.now() - timedelta(days=days)

    def _session(self, user=None, platform="ios", last_used_ago=1, status="active"):
        from apps.authentication.models import MobileSession

        if user is None:
            index = next(self._user_seq)
            user = Candidate.objects.create_user(
                email=f"mobile-user{index}-{id(self)}@example.com",
                password="testpass123",
            )
        now = timezone.now()
        return MobileSession.objects.create(
            user=user,
            device_id=f"device-{next(self._user_seq)}",
            platform=platform,
            auth_method="password",
            status=status,
            last_used_at=self._ago(last_used_ago) if last_used_ago is not None else None,
            idle_expires_at=now + timedelta(days=30),
            absolute_expires_at=now + timedelta(days=90),
        )

    def _report(self):
        return build_daily_application_report(report_date=self.report_date)

    def test_a_user_active_on_the_report_day_is_counted(self):
        self._session(last_used_ago=1)

        mobile = self._report()["mobile"]

        self.assertEqual(mobile["day"], 1)
        self.assertEqual(mobile["all_time"], 1)

    def test_a_user_with_two_devices_is_counted_once(self):
        candidate = Candidate.objects.create_user(
            email=f"mobile-shared-{id(self)}@example.com", password="testpass123"
        )
        self._session(user=candidate, platform="ios", last_used_ago=1)
        self._session(user=candidate, platform="android", last_used_ago=1)

        mobile = self._report()["mobile"]

        self.assertEqual(mobile["day"], 1)
        self.assertEqual(mobile["ios_day"] + mobile["android_day"], 2)

    def test_a_session_last_used_outside_the_day_window_is_excluded(self):
        self._session(last_used_ago=10)

        mobile = self._report()["mobile"]

        self.assertEqual(mobile["day"], 0)
        self.assertEqual(mobile["all_time"], 1)

    def test_revoked_sessions_are_not_counted(self):
        self._session(last_used_ago=1, status="revoked")

        mobile = self._report()["mobile"]

        self.assertEqual(mobile["day"], 0)
        self.assertEqual(mobile["all_time"], 0)

    def test_platform_split_matches_the_day_total(self):
        self._session(platform="ios", last_used_ago=1)
        self._session(platform="android", last_used_ago=1)
        self._session(platform="android", last_used_ago=1)

        mobile = self._report()["mobile"]

        self.assertEqual(mobile["day"], 3)
        self.assertEqual(mobile["ios_day"], 1)
        self.assertEqual(mobile["android_day"], 2)
