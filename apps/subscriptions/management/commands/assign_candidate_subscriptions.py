"""
Management command to retroactively assign the Free subscription plan
and its features to all existing candidates who don't have one yet.

Run after deploying the new candidate subscription model:

    python manage.py assign_candidate_subscriptions

Options:
    --dry-run   Show what would happen without making changes.

This command is idempotent — candidates who already have a subscription
are skipped.  No existing subscription data is modified or deleted.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.authentication.models import Candidate
from apps.subscriptions.models import CandidateSubscription
from apps.subscriptions.services import SubscriptionService


class Command(BaseCommand):
    help = (
        "Assign the Free subscription plan to all existing candidates "
        "who do not yet have a subscription."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE ===\n"))

        free_plan = SubscriptionService.get_default_candidate_plan()
        if free_plan is None:
            self.stdout.write(
                self.style.ERROR(
                    "Candidate Free plan not found. "
                    "Run 'python manage.py seed_subscriptions' first."
                )
            )
            return

        # Find candidates without any subscription
        candidates_with_sub = CandidateSubscription.objects.values_list(
            "candidate_id", flat=True
        )
        unassigned = Candidate.objects.exclude(id__in=candidates_with_sub)

        total = unassigned.count()

        if total == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "All candidates already have a subscription. Nothing to do."
                )
            )
            return

        self.stdout.write(
            f"Found {total} candidate(s) without a subscription."
        )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"\nWould assign '{free_plan.name}' plan to {total} candidate(s)."
                )
            )
            for candidate in unassigned[:10]:
                self.stdout.write(f"  - {candidate.email}")
            if total > 10:
                self.stdout.write(f"  ... and {total - 10} more")
            return

        assigned = 0
        failed = 0

        for candidate in unassigned.iterator(chunk_size=500):
            try:
                with transaction.atomic():
                    SubscriptionService.create_candidate_subscription(
                        candidate, plan=free_plan
                    )
                assigned += 1
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Failed to assign subscription for {candidate.email}: {e}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Assigned: {assigned}, Failed: {failed}, Total: {total}"
            )
        )
