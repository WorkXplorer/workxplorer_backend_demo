from django.core.management.base import BaseCommand

from apps.domain.services.sector_classification import (
    DEFAULT_BATCH_SIZE,
    classify_domain_sectors,
)


class Command(BaseCommand):
    help = (
        "Classify Domain records against the live stat.uz sector list "
        "(new/unclassified domains, and domains whose sector was removed "
        "upstream). Also runs automatically on a monthly schedule."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Domains per LLM call (default: {DEFAULT_BATCH_SIZE})",
        )

    def handle(self, *args, **options):
        result = classify_domain_sectors(batch_size=options["batch_size"])

        status = result.get("status")
        if status == "already_running":
            self.stdout.write(self.style.WARNING("Classification already running, skipped."))
            return
        if status == "failed":
            self.stderr.write(self.style.ERROR(f"Classification failed: {result.get('reason')}"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Classified {result.get('classified', 0)}/{result.get('candidates', 0)} "
                f"domains ({result.get('failed_batches', 0)} failed batches)."
            )
        )
