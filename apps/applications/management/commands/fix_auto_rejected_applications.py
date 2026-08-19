"""
Management command to fix applications that were incorrectly auto-rejected
to OFFER_REJECTED status instead of REJECTED status.

Background:
    Migration 0019 created the OFFER_REJECTED StatusCategory but didn't update
    existing companies' ApplicationStatusModel rows. This caused the
    _auto_reject_application() function to sometimes pick OFFER_REJECTED
    (which was still in the REJECTED category) instead of the actual REJECTED
    status when auto-rejecting low-scoring applications.

Usage:
    python manage.py fix_auto_rejected_applications
    python manage.py fix_auto_rejected_applications --dry-run
    python manage.py fix_auto_rejected_applications --application-id=<UUID>
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix applications incorrectly auto-rejected to OFFER_REJECTED instead of REJECTED"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Only show what would be fixed without making changes",
        )
        parser.add_argument(
            '--application-id',
            type=str,
            help="Fix a specific application by ID (UUID)",
        )

    def handle(self, *args, **options):
        from apps.applications.models import JobApplication, ApplicationStatusModel, StatusCategory

        dry_run = options.get('dry_run', False)
        app_id_filter = options.get('application_id')

        # Find applications that were auto-rejected (notes contain "Auto-rejected")
        # but are in OFFER_REJECTED status instead of REJECTED
        queryset = JobApplication.objects.filter(
            recruiter_notes__icontains='Auto-rejected by AI evaluation',
            status='OFFER_REJECTED',
        ).select_related('vacancy__company')

        if app_id_filter:
            queryset = queryset.filter(id=app_id_filter)

        total = queryset.count()
        self.stdout.write(f"Found {total} applications incorrectly set to OFFER_REJECTED\n")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No applications need fixing."))
            return

        fixed_count = 0
        for application in queryset:
            company = application.vacancy.company
            
            # Find the actual REJECTED status for this company
            rejected_status = (
                ApplicationStatusModel.objects.filter(
                    company=company,
                    category__key=StatusCategory.REJECTED,
                    key='REJECTED',
                    is_active=True,
                )
                .first()
            )

            if not rejected_status:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠ Application {application.id}: No REJECTED status found "
                        f"for company '{company.name}'. Skipping."
                    )
                )
                continue

            if dry_run:
                self.stdout.write(
                    f"  [DRY-RUN] Would fix application {application.id}: "
                    f"OFFER_REJECTED → {rejected_status.key} "
                    f"(Company: {company.name}, Vacancy: {application.vacancy.title})"
                )
                fixed_count += 1
                continue

            # Fix the application
            with transaction.atomic():
                old_status = application.status
                application.status = rejected_status.key
                application.save(update_fields=['status', 'updated_at'])

                # Update the recruiter notes to clarify the fix
                timestamp = application.updated_at.strftime("%Y-%m-%d %H:%M")
                fix_note = (
                    f"\n[{timestamp}] [SYSTEM FIX] Status corrected from '{old_status}' "
                    f"to '{rejected_status.key}'. Original auto-rejection was incorrectly "
                    f"applied with OFFER_REJECTED due to a category mapping bug (migration 0019)."
                )
                if application.recruiter_notes:
                    application.recruiter_notes += fix_note
                else:
                    application.recruiter_notes = fix_note
                application.save(update_fields=['recruiter_notes', 'updated_at'])

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ Fixed application {application.id}: "
                    f"{old_status} → {rejected_status.key} "
                    f"(Company: {company.name})"
                )
            )
            fixed_count += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\nDry run complete. {fixed_count} applications would be fixed.")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"\nDone. {fixed_count} applications fixed.")
            )
