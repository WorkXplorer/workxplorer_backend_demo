from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.authentication.models import Candidate
from apps.resumes.models import Resume, ResumeExperience
from apps.student_analytics.models import StudentAnalytics
from apps.student_analytics.services.salary_calculator import (
    _get_experience_percentile,
    _is_period_stale,
    calculate_salary,
)

_now = timezone.now()
CURRENT_QUARTER_LABEL = f"{_now.year}-Q{(_now.month - 1) // 3 + 1}"


class ExperiencePercentileTests(TestCase):

    def test_zero_months(self):
        self.assertEqual(_get_experience_percentile(0), Decimal("0.10"))

    def test_less_than_one_year(self):
        self.assertEqual(_get_experience_percentile(11), Decimal("0.10"))

    def test_one_year(self):
        self.assertEqual(_get_experience_percentile(12), Decimal("0.25"))

    def test_three_years(self):
        self.assertEqual(_get_experience_percentile(36), Decimal("0.50"))

    def test_five_years(self):
        self.assertEqual(_get_experience_percentile(60), Decimal("0.65"))

    def test_eight_years(self):
        self.assertEqual(_get_experience_percentile(96), Decimal("0.80"))

    def test_twelve_years(self):
        self.assertEqual(_get_experience_percentile(144), Decimal("0.90"))

    def test_eighteen_years_and_beyond_has_no_ceiling_tier(self):
        # This is the tier that didn't exist before: experience keeps
        # mapping to a higher percentile instead of capping at 5 years.
        self.assertEqual(_get_experience_percentile(216), Decimal("0.97"))
        self.assertEqual(_get_experience_percentile(600), Decimal("0.97"))


class PeriodStalenessTests(TestCase):

    def test_current_quarter_is_not_stale(self):
        now = datetime(2026, 8, 19, tzinfo=dt_timezone.utc)
        self.assertFalse(_is_period_stale("2026-Q3", now=now))

    def test_far_past_quarter_is_stale(self):
        now = datetime(2026, 8, 19, tzinfo=dt_timezone.utc)
        self.assertTrue(_is_period_stale("2024-Q1", now=now))

    def test_unparseable_label_is_stale(self):
        self.assertTrue(_is_period_stale("not-a-period"))


class SalaryCalculatorTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.candidate = Candidate.objects.create_user(
            email="salarytest@example.com", password="testpass123"
        )
        cls.resume = Resume.objects.create(
            candidate=cls.candidate,
            title="Test Resume",
            description="Developer",
        )
        cls.analytics = StudentAnalytics.objects.create(
            candidate=cls.candidate,
            resume=cls.resume,
            target_role="Python Developer",
        )

        today = date.today()
        ResumeExperience.objects.create(
            resume=cls.resume,
            company="Acme",
            role="Junior Dev",
            start_date=date(today.year - 2, 1, 1),
            end_date=today,
        )

    @patch(
        "apps.student_analytics.services.salary_calculator._get_sector_reference",
        return_value=None,
    )
    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_calculate_salary_basic(self, mock_get_market, mock_sector_ref):
        mock_get_market.return_value = {
            "median_salary_uzs": Decimal("10000000"),
            "salary_from": Decimal("6000000"),
            "salary_to": Decimal("16000000"),
            "sample_count": 10,
        }

        result = calculate_salary(self.candidate, self.resume, "Python Developer")

        # 2 years experience -> [12, 36) months bracket -> 0.25 percentile
        self.assertEqual(result["current_salary"], "7500000.00")
        self.assertEqual(result["potential_salary"], "9000000.00")
        self.assertEqual(result["market_median"], "10000000.00")
        self.assertEqual(result["match_percentage"], "75.0")
        self.assertEqual(result["currency"], "UZS")
        self.assertIsNone(result["sector_reference_salary"])
        self.assertTrue(result["experience_months"] >= 24)

    @patch(
        "apps.student_analytics.services.salary_calculator._get_sector_reference",
        return_value=None,
    )
    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_calculate_salary_zero_experience(self, mock_get_market, mock_sector_ref):
        mock_get_market.return_value = {
            "median_salary_uzs": Decimal("15000000"),
            "salary_from": Decimal("9000000"),
            "salary_to": Decimal("24000000"),
            "sample_count": 5,
        }

        candidate = Candidate.objects.create_user(
            email="zeroexp@example.com", password="testpass123"
        )
        resume = Resume.objects.create(
            candidate=candidate,
            title="No Exp Resume",
            description="Newbie",
        )

        result = calculate_salary(candidate, resume, "Backend Developer")

        # 0 months -> entry tier -> exactly the p10 anchor (salary_from)
        self.assertEqual(result["current_salary"], "9000000.00")
        self.assertEqual(result["potential_salary"], "11250000.00")
        self.assertEqual(result["match_percentage"], "60.0")
        self.assertEqual(result["experience_months"], 0)

    @patch(
        "apps.student_analytics.services.salary_calculator._get_sector_reference",
        return_value=None,
    )
    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_calculate_salary_veteran_is_no_longer_capped(self, mock_get_market, mock_sector_ref):
        """
        The old model capped everyone with 5+ years at the same 1.2x-median
        multiplier, so a 30-year veteran and a 5-year hire got an identical
        ceiling. The percentile model has no such ceiling: 30 years lands at
        the top tier (0.97) and extrapolates *above* the observed p90.
        """
        mock_get_market.return_value = {
            "median_salary_uzs": Decimal("20000000"),
            "salary_from": Decimal("12000000"),
            "salary_to": Decimal("32000000"),
            "sample_count": 20,
        }

        candidate = Candidate.objects.create_user(
            email="veteran@example.com", password="testpass123"
        )
        resume = Resume.objects.create(
            candidate=candidate,
            title="Veteran Resume",
            description="Expert",
        )
        today = date.today()
        ResumeExperience.objects.create(
            resume=resume,
            company="BigCo",
            role="Principal Engineer",
            start_date=date(today.year - 30, 1, 1),
            end_date=today,
        )

        result = calculate_salary(candidate, resume, "Principal Engineer")

        # 0.97 percentile, extrapolated beyond salary_to (32M) -- the old
        # model's hard ceiling here was exactly 20M * 1.2 = 24M.
        self.assertEqual(result["current_salary"], "34100000.00")
        self.assertGreater(Decimal(result["current_salary"]), Decimal("32000000"))
        self.assertTrue(result["experience_months"] >= 360)

    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_calculate_salary_zero_median(self, mock_get_market):
        mock_get_market.return_value = {
            "median_salary_uzs": Decimal("0"),
            "sample_count": 0,
        }

        result = calculate_salary(self.candidate, self.resume, "No Role")
        self.assertEqual(result["match_percentage"], "0.0")
        self.assertEqual(result["current_salary"], "0.00")

    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_calculate_salary_none_market(self, mock_get_market):
        mock_get_market.return_value = None

        result = calculate_salary(self.candidate, self.resume, "Unknown Role")
        self.assertEqual(result, {"error": "insufficient_data"})

    @patch("apps.student_analytics.services.salary_calculator._get_sector_reference")
    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_calculate_salary_blends_toward_sector_reference_when_sample_thin(
        self, mock_get_market, mock_sector_ref
    ):
        mock_get_market.return_value = {
            "median_salary_uzs": Decimal("10000000"),
            "salary_from": Decimal("6000000"),
            "salary_to": Decimal("16000000"),
            "sample_count": 2,  # thin -- alpha = min(0.85, 2/20) = 0.10
        }
        mock_sector_ref.return_value = {
            "avg_salary_uzs": Decimal("20000000"),
            "period_label": "2026-Q2",
        }

        candidate = Candidate.objects.create_user(
            email="thinsample@example.com", password="testpass123"
        )
        resume = Resume.objects.create(
            candidate=candidate, title="Thin Sample Resume", description="x"
        )

        result = calculate_salary(candidate, resume, "Niche Role")

        # blended_median = 0.10*10M + 0.90*20M = 19M
        self.assertEqual(result["market_median"], "19000000.00")
        self.assertEqual(result["sector_reference_salary"], "20000000.00")
        self.assertEqual(result["sector_reference_period"], "2026-Q2")
        # 0 experience -> p10 anchor, scaled by 19M/10M = 1.9x -> 6M*1.9
        self.assertEqual(result["current_salary"], "11400000.00")

    @patch("apps.student_analytics.services.salary_calculator._get_sector_reference")
    @patch("apps.student_analytics.services.salary_calculator.get_market_salary_for_role")
    def test_sector_reference_keeps_some_pull_even_with_large_sample(
        self, mock_get_market, mock_sector_ref
    ):
        mock_get_market.return_value = {
            "median_salary_uzs": Decimal("10000000"),
            "salary_from": Decimal("6000000"),
            "salary_to": Decimal("16000000"),
            "sample_count": 100,  # large -- alpha caps at 0.85, not 1.0
        }
        mock_sector_ref.return_value = {
            "avg_salary_uzs": Decimal("20000000"),
            "period_label": "2026-Q2",
        }

        result = calculate_salary(self.candidate, self.resume, "Python Developer")

        # blended_median = 0.85*10M + 0.15*20M = 11.5M -- never fully 10M,
        # even at a well-sampled role query.
        self.assertEqual(result["market_median"], "11500000.00")


class SectorReferenceIgnoresResumeDomainTests(TestCase):
    """
    resume.domain can be mis-assigned (candidate self-select or AI resume
    generation getting it wrong). Sector blending must derive the sector
    from target_role text instead, never from resume.domain -- otherwise a
    mistagged candidate gets anchored to the wrong sector's nominal salary.
    """

    def test_uses_target_role_derived_sector_not_resume_domain(self):
        from apps.domain.models import Domain
        from apps.general.models import StatUzSectorSalary

        wrong_domain = Domain.objects.create(name="Finance Domain", sector_code="237")
        right_domain = Domain.objects.create(name="IT Domain", sector_code="236")

        StatUzSectorSalary.objects.create(
            sector_code="237",
            sector_name="Financial and insurance activities",
            period_type="quarterly",
            period_label=CURRENT_QUARTER_LABEL,
            avg_salary_uzs=Decimal("30000000"),
            source_dataset_id="506",
        )
        StatUzSectorSalary.objects.create(
            sector_code="236",
            sector_name="Information and communication",
            period_type="quarterly",
            period_label=CURRENT_QUARTER_LABEL,
            avg_salary_uzs=Decimal("17000000"),
            source_dataset_id="506",
        )

        candidate = Candidate.objects.create_user(
            email="mistagged@example.com", password="testpass123"
        )
        # resume.domain is deliberately the WRONG domain, simulating the bug.
        resume = Resume.objects.create(
            candidate=candidate, title="x", description="x", domain=wrong_domain
        )

        with patch(
            "apps.resumes.services.resume_generation.DomainMatcher.find_matching_domain"
        ) as mock_match, patch(
            "apps.student_analytics.services.salary_calculator.get_market_salary_for_role"
        ) as mock_market:
            mock_match.return_value = {"id": right_domain.id, "name": right_domain.name}
            mock_market.return_value = {
                "median_salary_uzs": Decimal("10000000"),
                "salary_from": Decimal("6000000"),
                "salary_to": Decimal("16000000"),
                "sample_count": 2,
            }
            result = calculate_salary(candidate, resume, "System Analyst")

        # Anchored to the IT sector (236, 17M) resolved from target_role,
        # never the Finance sector (237, 30M) that resume.domain points to.
        self.assertEqual(result["sector_reference_salary"], "17000000.00")
