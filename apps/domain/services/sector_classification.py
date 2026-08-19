"""
Classifies Domain records against the live stat.uz sector list.

Runs monthly (see apps.general.services.scheduler) and via
`manage.py classify_domain_sectors`. A single pass:

1. Fetches the current sector list straight from stat.uz (not our synced
   copy), so it reflects renames/additions/removals immediately rather than
   waiting on the separate weekly salary sync.
2. Finds domains that need (re)classification: never classified
   (sector_code is null), or classified against a sector_code that no
   longer exists upstream (orphaned by a removal).
3. Classifies them in small batches via the LLM, validating every returned
   (domain_id, sector_code) pair against what was actually asked for before
   writing anything -- a hallucinated id or code is dropped, not trusted.

A domain the model can't confidently place is left with sector_code=null,
which naturally requeues it for the next run (useful since a newly added
sector might fit it later) rather than requiring a separate "permanently
unclassifiable" flag.
"""

import logging

from django.core.cache import cache

from apps.ai.services.ai_provider_client import AIProviderClient
from apps.general.services.stat_uz_client import fetch_sector_salary_table
from utils.prompt_sanitizer import sanitize_prompt_value

logger = logging.getLogger(__name__)

LOCK_KEY = "domain_sector_classification_lock"
LOCK_TIMEOUT = 15 * 60
DEFAULT_BATCH_SIZE = 25

ai_client = AIProviderClient()


def _acquire_lock():
    return cache.add(LOCK_KEY, "1", timeout=LOCK_TIMEOUT)


def _release_lock():
    cache.delete(LOCK_KEY)


def _get_valid_sectors():
    """
    {sector_code: sector_name} for every sector stat.uz currently publishes,
    fetched live so renames/additions/removals are picked up immediately.
    """
    raw_sectors = fetch_sector_salary_table()
    valid = {}
    for sector in raw_sectors or []:
        sector_id = sector.get("id")
        if sector_id is None:
            continue
        sector_code = str(sector_id)
        valid[sector_code] = sector.get("name_en") or sector.get("name") or sector_code
    return valid


def _domains_needing_classification(valid_sector_codes):
    from apps.domain.models import Domain

    return (
        Domain.objects.filter(sector_code__isnull=True)
        | Domain.objects.exclude(sector_code__isnull=True).exclude(
            sector_code__in=valid_sector_codes
        )
    ).distinct()


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _build_classification_prompt(domains, valid_sectors):
    domain_lines = []
    for domain in domains:
        parts = [
            sanitize_prompt_value(domain.name, max_length=200),
            sanitize_prompt_value(domain.name_en or "", max_length=200),
            sanitize_prompt_value(domain.name_ru or "", max_length=200),
            sanitize_prompt_value(domain.description or "", max_length=300),
        ]
        label = " / ".join(p for p in parts if p)
        domain_lines.append(f'- id="{domain.id}": {label}')

    sector_lines = [
        f'- code="{code}": {name}' for code, name in sorted(valid_sectors.items())
    ]

    return (
        "You are classifying professional domains into official economic "
        "sector categories published by Uzbekistan's National Statistics "
        "Committee.\n\n"
        "Domains to classify:\n" + "\n".join(domain_lines) + "\n\n"
        "Valid sector categories (choose only from this list):\n"
        + "\n".join(sector_lines) + "\n\n"
        "For each domain, pick the single best-fitting sector code. If none "
        "genuinely fit, use null. Respond with ONLY a JSON object mapping "
        'each domain id (as a string) to its sector code (as a string) or '
        'null, e.g. {"<domain_id>": "<sector_code>", "<domain_id_2>": null}. '
        "No other text."
    )


def _classify_batch(domains, valid_sectors):
    """
    Returns (assignments, ok). `assignments` is {domain_id: sector_code} for
    validated pairs only -- a domain omitted from the response, or assigned
    an id/code we didn't offer, is simply left out (unclassified until the
    next run). `ok` is False only when the batch itself failed (request
    error or unparseable/malformed response), as opposed to a batch that
    legitimately classified zero domains.
    """
    requested_ids = {str(d.id) for d in domains}
    prompt = _build_classification_prompt(domains, valid_sectors)

    try:
        response = ai_client.chat_completion(
            [
                {
                    "role": "system",
                    "content": "You output strict JSON only, no prose, no code fences.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            json_mode=True,
        )
        raw_content = response["choices"][0]["message"]["content"]
        parsed = ai_client.parse_json_response(raw_content)
    except Exception:
        logger.warning(
            "Domain sector classification batch failed (domains=%s)",
            sorted(requested_ids),
            exc_info=True,
        )
        return {}, False

    if not isinstance(parsed, dict):
        logger.warning("Domain sector classification returned non-object JSON: %r", parsed)
        return {}, False

    validated = {}
    for domain_id, sector_code in parsed.items():
        if domain_id not in requested_ids:
            logger.warning("Ignoring hallucinated domain id in classification response: %s", domain_id)
            continue
        if sector_code is None:
            continue
        sector_code = str(sector_code)
        if sector_code not in valid_sectors:
            logger.warning(
                "Ignoring hallucinated sector code '%s' for domain %s", sector_code, domain_id
            )
            continue
        validated[domain_id] = sector_code

    return validated, True


def classify_domain_sectors(batch_size=DEFAULT_BATCH_SIZE):
    """
    Main entrypoint, used by both the monthly scheduled job and
    `manage.py classify_domain_sectors`. Safe to call concurrently -- a
    second caller while one run is in progress is a no-op, not a duplicate
    run racing the first.
    """
    from apps.domain.models import Domain

    if not _acquire_lock():
        logger.info("Domain sector classification already running, skipping.")
        return {"status": "already_running"}

    try:
        try:
            valid_sectors = _get_valid_sectors()
        except Exception:
            logger.warning("Could not fetch stat.uz sector list, aborting classification run", exc_info=True)
            return {"status": "failed", "reason": "stat_uz_fetch_failed"}

        if not valid_sectors:
            logger.warning("stat.uz returned no sectors, aborting classification run")
            return {"status": "failed", "reason": "no_sectors_returned"}

        candidates = list(_domains_needing_classification(valid_sectors.keys()))
        if not candidates:
            return {"status": "completed", "candidates": 0, "classified": 0, "failed_batches": 0}

        classified = 0
        failed_batches = 0

        for batch in _chunk(candidates, batch_size):
            assignments, ok = _classify_batch(batch, valid_sectors)
            if not ok:
                failed_batches += 1

            for domain_id, sector_code in assignments.items():
                updated = Domain.objects.filter(id=domain_id).update(sector_code=sector_code)
                if updated:
                    classified += 1

        logger.info(
            "Domain sector classification: %s candidates, %s classified, %s failed batches",
            len(candidates),
            classified,
            failed_batches,
        )
        return {
            "status": "completed" if failed_batches == 0 else "partial",
            "candidates": len(candidates),
            "classified": classified,
            "failed_batches": failed_batches,
        }
    finally:
        _release_lock()
