from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.domain.models import Domain
from apps.domain.services import sector_classification

SAMPLE_RAW_SECTORS = [
    {"id": 236, "name_en": "Information and communication"},
    {"id": 242, "name_en": "Education"},
]


def _chat_response(text):
    return {"choices": [{"message": {"content": text}}]}


class GetValidSectorsTests(TestCase):
    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_builds_code_to_name_map(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        result = sector_classification._get_valid_sectors()
        self.assertEqual(result, {"236": "Information and communication", "242": "Education"})


class DomainsNeedingClassificationTests(TestCase):
    def test_includes_unclassified_and_orphaned_domains(self):
        never_classified = Domain.objects.create(name="IT")
        orphaned = Domain.objects.create(name="Mining", sector_code="999")
        Domain.objects.create(name="Education", sector_code="242")  # up to date

        candidates = set(
            sector_classification._domains_needing_classification({"236", "242"})
        )

        self.assertIn(never_classified, candidates)
        self.assertIn(orphaned, candidates)
        self.assertEqual(len(candidates), 2)


class ClassifyDomainSectorsTests(TestCase):
    def tearDown(self):
        cache.delete(sector_classification.LOCK_KEY)

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_no_candidates_skips_llm_call(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        Domain.objects.create(name="Education", sector_code="242")

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            result = sector_classification.classify_domain_sectors()

        mock_chat.assert_not_called()
        self.assertEqual(result, {"status": "completed", "candidates": 0, "classified": 0, "failed_batches": 0})

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_valid_assignment_is_written(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        domain = Domain.objects.create(name="IT Development")

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            mock_chat.return_value = _chat_response(f'{{"{domain.id}": "236"}}')
            result = sector_classification.classify_domain_sectors(batch_size=25)

        domain.refresh_from_db()
        self.assertEqual(domain.sector_code, "236")
        self.assertEqual(result["classified"], 1)
        self.assertEqual(result["failed_batches"], 0)

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_hallucinated_domain_id_is_ignored(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        domain = Domain.objects.create(name="IT Development")

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            mock_chat.return_value = _chat_response('{"not-a-real-id": "236"}')
            result = sector_classification.classify_domain_sectors()

        domain.refresh_from_db()
        self.assertIsNone(domain.sector_code)
        self.assertEqual(result["classified"], 0)

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_hallucinated_sector_code_is_ignored(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        domain = Domain.objects.create(name="IT Development")

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            mock_chat.return_value = _chat_response(f'{{"{domain.id}": "999-does-not-exist"}}')
            result = sector_classification.classify_domain_sectors()

        domain.refresh_from_db()
        self.assertIsNone(domain.sector_code)
        self.assertEqual(result["classified"], 0)

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_batch_failure_is_tracked_and_does_not_raise(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        Domain.objects.create(name="IT Development")

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            mock_chat.side_effect = RuntimeError("LLM unavailable")
            result = sector_classification.classify_domain_sectors()

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["failed_batches"], 1)
        self.assertEqual(result["classified"], 0)

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_stat_uz_fetch_failure_aborts_run(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("network error")

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            result = sector_classification.classify_domain_sectors()

        mock_chat.assert_not_called()
        self.assertEqual(result, {"status": "failed", "reason": "stat_uz_fetch_failed"})

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_concurrent_run_is_skipped(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        cache.set(sector_classification.LOCK_KEY, "1", timeout=60)

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            result = sector_classification.classify_domain_sectors()

        mock_chat.assert_not_called()
        self.assertEqual(result, {"status": "already_running"})

    @patch("apps.domain.services.sector_classification.fetch_sector_salary_table")
    def test_orphaned_domain_is_reclassified(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_RAW_SECTORS
        domain = Domain.objects.create(name="Mining Co", sector_code="999")  # no longer valid

        with patch.object(sector_classification.ai_client, "chat_completion") as mock_chat:
            mock_chat.return_value = _chat_response(f'{{"{domain.id}": "236"}}')
            result = sector_classification.classify_domain_sectors()

        domain.refresh_from_db()
        self.assertEqual(domain.sector_code, "236")
        self.assertEqual(result["classified"], 1)
