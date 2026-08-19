"""
Rebuild daily report snapshots for past dates.

Run once after deploying the snapshot table so charts have some history to draw
before a month of waiting:

    python manage.py backfill_report_snapshots --days 90
    python manage.py backfill_report_snapshots --from 2026-06-01 --to 2026-06-30

READ THIS BEFORE TRUSTING BACKFILLED ROWS. A rebuilt payload is not the payload
that day would have produced. Only the parts derived from timestamped rows come
back correctly — applications, signups, per-company and per-university counts,
the day's status mix. The point-in-time parts are recomputed as they are *now*
and silently attributed to a past date:

    churn, marketplace.open_vacancies, marketplace.idle_vacancies,
    marketplace.saved_not_applied, recruiters.recent, statuses.all_time,
    funnel (views, reviewed, hired are all current totals)

So a backfilled row says today's churn rate was also June's. Rows written here
are therefore tagged ``"backfilled": true`` in the payload, and anything
plotting a trend should drop those keys for tagged rows rather than draw a flat
line and call it history.

By default existing snapshots are left alone, so a backfill can never overwrite
a real one with a reconstruction. ``--overwrite`` lifts that, and should
essentially never be used.
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.applications.models import DailyReportSnapshot
from apps.applications.services.daily_report import build_daily_application_report

# Payload sections that describe "right now" and are meaningless when rebuilt
# for a past date. Named here so the warning and the tag stay in one place.
POINT_IN_TIME_KEYS = (
    "churn",
    "recruiters",
    "funnel",
    "marketplace",
)


class Command(BaseCommand):
    help = "Rebuild daily report snapshots for past dates (see module docstring)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            help="Backfill this many days ending yesterday.",
        )
        parser.add_argument("--from", dest="start", help="First day, YYYY-MM-DD.")
        parser.add_argument("--to", dest="end", help="Last day, YYYY-MM-DD.")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing snapshots with reconstructions (almost never right).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be written without writing it.",
        )

    def _window(self, options) -> tuple[date, date]:
        yesterday = timezone.localdate() - timedelta(days=1)

        if options["days"]:
            if options["start"] or options["end"]:
                raise CommandError("Use either --days or --from/--to, not both.")
            if options["days"] < 1:
                raise CommandError("--days must be at least 1.")
            return yesterday - timedelta(days=options["days"] - 1), yesterday

        if not options["start"]:
            raise CommandError("Give either --days or --from (with optional --to).")

        try:
            start = date.fromisoformat(options["start"])
            end = date.fromisoformat(options["end"]) if options["end"] else yesterday
        except ValueError as exc:
            raise CommandError(f"Invalid date: {exc}") from exc

        if start > end:
            raise CommandError("--from must not be after --to.")
        if end > yesterday:
            raise CommandError("Refusing to backfill today or the future.")
        return start, end

    def handle(self, *args, **options):
        start, end = self._window(options)
        existing = set(
            DailyReportSnapshot.objects.filter(
                report_date__gte=start, report_date__lte=end
            ).values_list("report_date", flat=True)
        )

        self.stdout.write(
            self.style.WARNING(
                f"Rebuilding {(end - start).days + 1} day(s) from {start} to {end}.\n"
                f"These sections will hold TODAY's values, not the day's: "
                f"{', '.join(POINT_IN_TIME_KEYS)}."
            )
        )

        written = skipped = 0
        day = start
        while day <= end:
            if day in existing and not options["overwrite"]:
                skipped += 1
                day += timedelta(days=1)
                continue

            try:
                payload = build_daily_application_report(report_date=day)
            except Exception as exc:  # one bad day must not sink the whole range
                self.stderr.write(self.style.ERROR(f"{day}: build failed — {exc}"))
                day += timedelta(days=1)
                continue

            # Tagged so a reader can tell a reconstruction from a real capture.
            payload["backfilled"] = True

            if options["dry_run"]:
                self.stdout.write(
                    f"{day}: would write {payload['totals']['day']} applications"
                )
            else:
                DailyReportSnapshot.store(payload)
                self.stdout.write(
                    f"{day}: {payload['totals']['day']} applications"
                )
            written += 1
            day += timedelta(days=1)

        summary = f"{written} snapshot(s) {'planned' if options['dry_run'] else 'written'}"
        if skipped:
            summary += f", {skipped} existing left untouched"
        self.stdout.write(self.style.SUCCESS(summary))
