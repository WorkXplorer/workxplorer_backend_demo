from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _
from django.db import transaction

from apps.applications.models import StatusTemplate, ApplicationStatusModel


class Command(BaseCommand):
    help = _("Reset application statuses for a company to default template values")

    def add_arguments(self, parser):
        parser.add_argument(
            "company_id",
            type=str,
            help=_("The UUID of the company to reset statuses for"),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Show what would be deleted/created without making changes"),
        )

    def handle(self, *args, **options):
        company_id = options["company_id"]
        dry_run = options["dry_run"]

        self.stdout.write(
            f"{'[DRY RUN] ' if dry_run else ''}Resetting application statuses for company {company_id}..."
        )

        try:
            from apps.authentication.models import Company

            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            raise CommandError(_("Company with ID {} not found.").format(company_id))

        existing_count = ApplicationStatusModel.objects.filter(
            company=company
        ).count()

        if existing_count == 0:
            self.stdout.write(
                self.style.WARNING(
                    _("Company {} has no existing statuses.".format(company.name))
                )
            )

        template = StatusTemplate.objects.filter(is_default=True).first()
        if not template:
            raise CommandError(
                _("No default status template found. Please create one first.")
            )

        self.stdout.write(
            _("Found default template: {}").format(template.name)
        )
        self.stdout.write(
            _("Existing statuses to delete: {}").format(existing_count)
        )
        self.stdout.write(
            _("Statuses to create from template: {}").format(len(template.statuses))
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    _("\nDry run mode - no changes will be made.")
                )
            )
            return

        with transaction.atomic():
            ApplicationStatusModel.objects.filter(company=company).delete()
            self.stdout.write(
                self.style.SUCCESS(
                    _("Deleted {} existing statuses.").format(existing_count)
                )
            )

            result = template.apply_to_company(company)
            self.stdout.write(
                self.style.SUCCESS(
                    _("Created {} new statuses from template.").format(
                        result["statuses_created"]
                    )
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                _("\nStatus reset complete for company {}!").format(company.name)
            )
        )
