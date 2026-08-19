import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.student_analytics.models import VacancyRoadmapItem

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=VacancyRoadmapItem)
def _capture_pre_save_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.only('status').get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None


@receiver(post_save, sender=VacancyRoadmapItem)
def handle_vacancy_roadmap_item_verified(sender, instance, created, **kwargs):
    if created:
        return
    if instance.status != VacancyRoadmapItem.Status.VERIFIED:
        return
    old_status = getattr(instance, '_old_status', None)
    if old_status == VacancyRoadmapItem.Status.VERIFIED:
        return
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and 'status' not in update_fields:
        return

    if not instance.skill_id:
        return

    candidate = instance.roadmap.application.candidate

    other_items = VacancyRoadmapItem.objects.filter(
        skill_id=instance.skill_id,
        roadmap__application__candidate=candidate,
    ).exclude(id=instance.id).exclude(status=VacancyRoadmapItem.Status.VERIFIED)

    if not other_items.exists():
        return

    updated = other_items.update(status=VacancyRoadmapItem.Status.VERIFIED, updated_at=timezone.now())
    logger.info(
        "VacancyRoadmapItem %s verified for skill %s — synced %d other items for candidate %s",
        instance.id, instance.skill_id, updated, candidate.id,
    )
