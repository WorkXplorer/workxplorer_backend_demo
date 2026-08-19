from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from apps.general.services import hh_client, market_salary_cache


class PercentileTests(TestCase):
    def test_empty(self):
        self.assertIsNone(market_salary_cache._percentile([], 0.5))

    def test_median_matches_statistics(self):
        values = [1, 2, 3, 4, 5]
        self.assertEqual(market_salary_cache._percentile(values, 0.5), 3)

    def test_interpolates_between_points(self):
        values = [10, 20, 30, 40]
        # (4-1) * 0.5 = 1.5 -> between index 1 (20) and 2 (30)
        self.assertEqual(market_salary_cache._percentile(values, 0.5), 25)


class CalcAggregateTests(TestCase):
    def test_small_sample_uses_raw_min_max(self):
        salaries = [1_000_000, 5_000_000, 50_000_000]  # one wild outlier, tiny sample
        result = market_salary_cache._calc_aggregate(salaries)

        self.assertEqual(result["sample_count"], 3)
        self.assertEqual(result["salary_from"], Decimal("1000000"))
        self.assertEqual(result["salary_to"], Decimal("50000000"))

    def test_large_sample_trims_outliers_via_percentile(self):
        # 10 normal points clustered near 10M plus one extreme outlier.
        salaries = [9_000_000 + i * 100_000 for i in range(10)] + [200_000_000]
        result = market_salary_cache._calc_aggregate(salaries)

        self.assertEqual(result["sample_count"], 11)
        # The 200M outlier must not become salary_to once percentile trimming kicks in.
        self.assertLess(result["salary_to"], Decimal("200000000"))


class BlendWithPreviousTests(TestCase):
    def _previous(self, median, salary_from, salary_to):
        previous = Mock()
        previous.median_salary_uzs = Decimal(str(median))
        previous.salary_from = Decimal(str(salary_from))
        previous.salary_to = Decimal(str(salary_to))
        return previous

    def test_thin_new_sample_stays_close_to_previous(self):
        previous = self._previous(10_000_000, 8_000_000, 12_000_000)
        new_result = {
            "median_salary_uzs": Decimal("40000000"),
            "salary_from": Decimal("35000000"),
            "salary_to": Decimal("45000000"),
            "sample_count": 1,
            "source": "hh",
        }

        blended = market_salary_cache._blend_with_previous(new_result, previous)

        # With sample_count=1, alpha is floored low, so the blended median
        # should sit much closer to the previous snapshot than the new spike.
        self.assertLess(blended["median_salary_uzs"], Decimal("15000000"))
        self.assertGreater(blended["median_salary_uzs"], Decimal("10000000"))
        self.assertEqual(blended["sample_count"], 1)

    def test_richer_new_sample_moves_further_from_previous(self):
        previous = self._previous(10_000_000, 8_000_000, 12_000_000)
        new_result = {
            "median_salary_uzs": Decimal("40000000"),
            "salary_from": Decimal("35000000"),
            "salary_to": Decimal("45000000"),
            "sample_count": 15,
            "source": "hh",
        }

        blended = market_salary_cache._blend_with_previous(new_result, previous)

        self.assertGreater(blended["median_salary_uzs"], Decimal("20000000"))


class GetMarketSalaryForRoleTests(TestCase):
    @override_settings(MARKET_SALARY_CACHE_TTL_SECONDS=86400)
    @patch("apps.general.services.market_salary_cache._collect_hh_salaries")
    @patch("apps.general.services.market_salary_cache._collect_platform_salaries")
    def test_empty_fresh_pull_reuses_previous_snapshot(self, mock_platform, mock_hh):
        from apps.general.models import MarketSalaryCache

        MarketSalaryCache.objects.create(
            role="python developer",
            source="both",
            median_salary_uzs=Decimal("9000000"),
            salary_from=Decimal("7000000"),
            salary_to=Decimal("11000000"),
            sample_count=25,
        )
        # Force the TTL check to be treated as expired by directly clearing
        # any warm Django cache entry for this role.
        from django.core.cache import cache

        cache.delete("market_salary:python developer")

        mock_platform.return_value = []
        mock_hh.return_value = []

        with patch(
            "apps.general.services.market_salary_cache.get_salary_cache_ttl",
            return_value=-1,
        ):
            result = market_salary_cache.get_market_salary_for_role("Python Developer")

        self.assertIsNotNone(result)
        self.assertEqual(result["median_salary_uzs"], Decimal("9000000"))
        self.assertEqual(result["sample_count"], 25)


class HHClientOnlyWithSalaryTests(TestCase):
    @override_settings(HH_ACCESS_TOKEN="test-token")
    @patch("apps.general.services.hh_client.requests.get")
    def test_collect_hh_salaries_requests_only_with_salary(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [], "pages": 1}
        mock_get.return_value = mock_response

        hh_client.collect_hh_salaries(query="python", max_pages=1)

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["only_with_salary"], "true")
