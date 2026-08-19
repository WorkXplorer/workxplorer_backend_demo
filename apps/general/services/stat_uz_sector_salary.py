import logging

from django.db import transaction

from .stat_uz_client import fetch_sector_salary_table, parse_sector_salary_rows

logger = logging.getLogger(__name__)


def sync_stat_uz_sector_salaries(dataset_id=None):
    """
    Pull the full sector salary table from stat.uz and upsert it into
    StatUzSectorSalary. Idempotent: safe to run repeatedly (e.g. weekly),
    since rows are keyed on (sector_code, period_type, period_label).
    """
    from apps.general.models import StatUzSectorSalary

    raw_sectors = fetch_sector_salary_table(dataset_id=dataset_id)
    rows = parse_sector_salary_rows(raw_sectors, dataset_id=dataset_id)

    synced = 0
    with transaction.atomic():
        for row in rows:
            StatUzSectorSalary.objects.update_or_create(
                sector_code=row["sector_code"],
                period_type=row["period_type"],
                period_label=row["period_label"],
                defaults={
                    "sector_name": row["sector_name"],
                    "avg_salary_uzs": row["avg_salary_uzs"],
                    "source_dataset_id": row["source_dataset_id"],
                },
            )
            synced += 1

    logger.info("Synced %s stat.uz sector salary rows", synced)
    return synced


def get_latest_sector_salary(sector_code):
    """
    Return {"avg_salary_uzs": Decimal, "period_label": str} for the most
    recent period we have synced for a sector, or None if we have no data
    for it yet. Period labels are fixed-format "YYYY-Qn" strings, so
    lexicographic ordering sorts them chronologically.

    Deliberately returns the period_label alongside the value rather than a
    bare number: if a sector is renamed, removed, or replaced upstream, our
    copy just stops getting new periods for it (sync never deletes rows), so
    the caller needs the period to decide whether the figure is still fresh
    enough to trust as a sanity check rather than silently using a stale one.
    """
    from apps.general.models import StatUzSectorSalary

    if not sector_code:
        return None

    row = (
        StatUzSectorSalary.objects.filter(sector_code=str(sector_code))
        .order_by("-period_label")
        .first()
    )
    if row is None:
        return None
    return {"avg_salary_uzs": row.avg_salary_uzs, "period_label": row.period_label}
