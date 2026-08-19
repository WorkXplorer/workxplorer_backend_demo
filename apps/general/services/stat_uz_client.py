import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_STAT_UZ_BASE_URL = "https://siat.stat.uz"
DEFAULT_STAT_UZ_SALARY_DATASET_ID = "506"
DEFAULT_STAT_UZ_REQUEST_TIMEOUT = 15


def get_stat_uz_base_url():
    value = getattr(settings, "STAT_UZ_API_BASE_URL", DEFAULT_STAT_UZ_BASE_URL)
    return str(value or DEFAULT_STAT_UZ_BASE_URL).rstrip("/")


def get_stat_uz_salary_dataset_id():
    value = getattr(settings, "STAT_UZ_SALARY_DATASET_ID", DEFAULT_STAT_UZ_SALARY_DATASET_ID)
    return str(value or DEFAULT_STAT_UZ_SALARY_DATASET_ID)


def fetch_sector_salary_table(dataset_id=None):
    """
    Fetch the raw sector salary table from siat.stat.uz.

    Confirmed response shape (GET /api/sdmx/{dataset_id}/table/):
        [
          {
            "id": 236,
            "name": "...", "name_en": "Information and communication",
            "name_ru": "...", "name_uz": "...", "name_uzc": "...",
            "is_root": false, "map_code": null,
            "data": [{"2017-Q1": 835460.3}, {"2017-Q2": 835093.4}, ...]
          },
          ...
        ]

    Each entry in "data" is a single-key dict mapping a "YYYY-Qn" period
    label to the average monthly salary (UZS) for that sector/quarter.
    No auth is required; this is a public endpoint.
    """
    dataset_id = dataset_id or get_stat_uz_salary_dataset_id()
    url = f"{get_stat_uz_base_url()}/api/sdmx/{dataset_id}/table/"
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        timeout=DEFAULT_STAT_UZ_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def parse_sector_salary_rows(raw_sectors, dataset_id=None):
    """
    Flatten the raw stat.uz payload into a list of row dicts ready to upsert
    into StatUzSectorSalary: sector_code, sector_name, period_type,
    period_label, avg_salary_uzs, source_dataset_id.
    """
    dataset_id = dataset_id or get_stat_uz_salary_dataset_id()
    rows = []

    for sector in raw_sectors or []:
        sector_id = sector.get("id")
        if sector_id is None:
            continue
        sector_code = str(sector_id)
        sector_name = sector.get("name_en") or sector.get("name") or sector_code

        for entry in sector.get("data") or []:
            if not isinstance(entry, dict):
                continue
            for period_label, value in entry.items():
                if value is None:
                    continue
                try:
                    avg_salary_uzs = Decimal(str(value)).quantize(Decimal("0.01"))
                except (InvalidOperation, TypeError, ValueError):
                    logger.warning(
                        "Skipping unparseable stat.uz value for sector=%s period=%s: %r",
                        sector_code,
                        period_label,
                        value,
                    )
                    continue
                rows.append(
                    {
                        "sector_code": sector_code,
                        "sector_name": sector_name,
                        "period_type": "quarterly",
                        "period_label": period_label,
                        "avg_salary_uzs": avg_salary_uzs,
                        "source_dataset_id": dataset_id,
                    }
                )

    return rows
