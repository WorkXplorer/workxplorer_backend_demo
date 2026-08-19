"""
Manually build (and optionally send) the daily application report.

Useful for previewing the numbers or re-sending a day the scheduled job missed:

    python manage.py send_daily_application_report --dry-run
    python manage.py send_daily_application_report --date 2026-07-27
"""

import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.applications.services.daily_report import (
    build_daily_application_report,
    send_daily_application_report,
)


class Command(BaseCommand):
    help = "Build and send the daily job-application report to the Telegram group."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            dest="report_date",
            help="Day to report on in YYYY-MM-DD form (default: yesterday).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the payload without sending it to Telegram.",
        )

    def handle(self, *args, **options):
        report_date = None
        if options["report_date"]:
            try:
                report_date = date.fromisoformat(options["report_date"])
            except ValueError as exc:
                raise CommandError(f"Invalid --date value: {exc}") from exc

        payload = build_daily_application_report(report_date=report_date)
        self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))

        if options["dry_run"]:
            # To stderr, so `--dry-run > day.json` leaves stdout as valid JSON
            # for the bot's card preview to read.
            self.stderr.write(self.style.WARNING("Dry run — nothing sent."))
            return

        if send_daily_application_report(payload):
            self.stdout.write(self.style.SUCCESS("Report sent to Telegram."))
        else:
            raise CommandError("Report delivery failed — see logs for details.")
