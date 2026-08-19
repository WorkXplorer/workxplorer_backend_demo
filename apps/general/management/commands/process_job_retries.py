import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.general.services.job_queue_service import JobQueueService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process job queue retries for failed analytics jobs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Clean up old completed jobs (default: 30 days)",
        )
        parser.add_argument(
            "--cleanup-days",
            type=int,
            default=30,
            help="Number of days to keep completed jobs (default: 30)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--stats-only",
            action="store_true",
            help="Only show job statistics without processing",
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(
            self.style.NOTICE(f"Starting job queue processing at {start_time}")
        )

        # Show statistics
        stats = JobQueueService.get_job_statistics()
        self.stdout.write(self.style.NOTICE("\n=== Job Queue Statistics ==="))
        self.stdout.write(f"Total jobs: {stats['total']}")

        self.stdout.write("\nBy Status:")
        for status, count in stats["by_status"].items():
            self.stdout.write(f"  {status}: {count}")

        self.stdout.write("\nBy Type:")
        for job_type, statuses in stats["by_type"].items():
            self.stdout.write(f"  {job_type}:")
            for status, count in statuses.items():
                self.stdout.write(f"    {status}: {count}")

        if stats["failed_needing_attention"] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nJobs needing attention: {stats['failed_needing_attention']}"
                )
            )

        if options["stats_only"]:
            return

        if options["dry_run"]:
            self._handle_dry_run()
            return

        # Process retries
        self.stdout.write(self.style.NOTICE("\n=== Processing Retries ==="))
        results = JobQueueService.process_retry_jobs()

        self.stdout.write(f"Jobs processed: {results['processed']}")
        self.stdout.write(f"Jobs retried: {results['retried']}")
        self.stdout.write(f"Alerts sent: {results['alerts_sent']}")

        if results["errors"]:
            self.stdout.write(self.style.ERROR("\nErrors:"))
            for error in results["errors"]:
                self.stdout.write(f"  - {error}")

        # Cleanup old jobs if requested
        if options["cleanup"]:
            self.stdout.write(self.style.NOTICE("\n=== Cleaning Up Old Jobs ==="))
            deleted_count = JobQueueService.cleanup_old_completed_jobs(
                days_to_keep=options["cleanup_days"]
            )
            self.stdout.write(f"Deleted {deleted_count} old completed jobs")

        # Summary
        end_time = timezone.now()
        duration = (end_time - start_time).total_seconds()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nJob queue processing completed in {duration:.2f}s"
            )
        )

    def _handle_dry_run(self):
        """Show what would be done without making changes."""
        self.stdout.write(self.style.NOTICE("\n=== Dry Run Mode ==="))

        # Get jobs that would be retried
        retry_jobs = JobQueueService.get_pending_and_failed_jobs()
        self.stdout.write(f"Jobs that would be retried: {len(retry_jobs)}")

        for job in retry_jobs[:10]:  # Show first 10
            self.stdout.write(
                f"  - {job.job_type} | {job.target_date} | "
                f"{job.target_name or job.target_id} | "
                f"retries: {job.retry_count}"
            )

        if len(retry_jobs) > 10:
            self.stdout.write(f"  ... and {len(retry_jobs) - 10} more")

        # Get jobs that would trigger alerts
        alert_jobs = JobQueueService.get_jobs_requiring_alert()
        self.stdout.write(f"\nJobs that would trigger alerts: {len(alert_jobs)}")

        for job in alert_jobs[:5]:  # Show first 5
            self.stdout.write(
                f"  - {job.job_type} | {job.target_date} | "
                f"retries: {job.retry_count} | "
                f"error: {job.error_message[:50] if job.error_message else 'N/A'}..."
            )
