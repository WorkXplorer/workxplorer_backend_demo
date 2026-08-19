from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
 
from apps.authentication.models.consent import UserConsent
from apps.authentication.models.candidate import Candidate
from apps.authentication.models.recruiter import Recruiter, Company
 
 
class Command(BaseCommand):
    help = (
        'Backfill consenter_email for existing consent records and mark orphaned '
        'records (whose entity was deleted) with consenter_deleted=True.'
    )
 
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would change without writing anything.',
        )
 
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total_filled = 0
        total_marked = 0
 
        for model in [Candidate, Recruiter, Company]:
            ct = ContentType.objects.get_for_model(model)
            qs = UserConsent.objects.filter(content_type=ct)
 
            # ── Fill consenter_email for records whose entity still exists ──
            for instance in model.objects.all():
                email = (
                    getattr(instance, 'email', None)
                    or getattr(instance, 'name', None)
                    or str(instance.pk)
                )
                to_fill = qs.filter(object_id=str(instance.pk), consenter_email='')
                count = to_fill.count()
                if count and not dry_run:
                    to_fill.update(consenter_email=email)
                total_filled += count
 
            # ── Mark orphaned records ──
            existing_pks = set(str(pk) for pk in model.objects.values_list('pk', flat=True))
            orphaned = qs.filter(consenter_deleted=False).exclude(object_id__in=existing_pks)
            count = orphaned.count()
            if count and not dry_run:
                orphaned.update(consenter_deleted=True)
            total_marked += count
 
            if dry_run:
                self.stdout.write(f'{model.__name__}: {total_filled} email(s) to fill, {count} orphaned to mark.')
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'{model.__name__}: done.')
                )
 
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'Dry run — {total_filled} email(s) would be filled, '
                    f'{total_marked} record(s) would be marked deleted. '
                    f'Re-run without --dry-run to apply.'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Done. {total_filled} email(s) filled, '
                    f'{total_marked} orphaned record(s) marked as deleted.'
                )
            )