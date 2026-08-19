import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.applications.models import JobApplication, ApplicationDocument
from .models import Conversation, Message, MessageType
from .realtime import broadcast_message
from .services import render_default_message

logger = logging.getLogger(__name__)


def _create_conversation_sync(instance) -> None:
    """
    Synchronously create the Conversation + initial Message for *instance*.
    Called directly from the signal handler to guarantee the conversation
    is always created, regardless of RQ worker availability.
    """
    try:
        recruiter_id = instance.vacancy.created_by_id
        candidate_id = instance.candidate_id

        existing = (
            Conversation.objects.filter(
                candidate_id=candidate_id,
                recruiter_id=recruiter_id,
                application__isnull=True,
                vacancy_id=instance.vacancy_id,
            )
            .only("id", "application_id", "vacancy_id", "is_read_by_recruiter")
            .order_by()
            .first()
        )

        if existing:
            existing.application = instance
            existing.vacancy = None
            existing.is_read_by_recruiter = False
            existing.save(
                update_fields=["application", "vacancy", "is_read_by_recruiter", "updated_at"]
            )
            conversation = existing
            converted = True
        else:
            conversation = Conversation.objects.create(
                application=instance,
                candidate_id=candidate_id,
                recruiter_id=recruiter_id,
                is_read_by_recruiter=False,
                is_read_by_candidate=True,
            )
            converted = False

        cover_letter = instance.cover_letter
        if cover_letter and cover_letter.strip():
            message = Message.objects.create(
                conversation=conversation,
                sender_type="CANDIDATE",
                message_type=MessageType.COVER_LETTER,
                content=cover_letter,
                is_read=False,
            )
        else:
            vacancy_title = instance.vacancy.title if instance.vacancy else ""
            params = {"vacancy_title": vacancy_title}
            # The platform writes this line, not the candidate, so it is stored
            # as a key plus its values and rendered per reader. Baking the text
            # in at creation time froze it in the applicant's language, which
            # the recruiter then had to read.
            message = Message.objects.create(
                conversation=conversation,
                sender_type="CANDIDATE",
                message_type=MessageType.TEXT,
                content=render_default_message("candidate_applied_to_vacancy", params),
                metadata={
                    "message_key": "candidate_applied_to_vacancy",
                    "message_params": params,
                },
                is_read=False,
            )

        # A recruiter with the chat open sees the application arrive without
        # reloading.
        broadcast_message(message, conversation=conversation)

        logger.info(
            "%s conversation %s for application %s between candidate %s and recruiter %s",
            "Converted headhunting" if converted else "Created",
            conversation.id,
            instance.id,
            candidate_id,
            recruiter_id,
        )

    except Exception:
        logger.error(
            "Failed to create conversation for application %s",
            instance.id,
            exc_info=True,
        )


@receiver(post_save, sender=JobApplication)
def create_conversation_on_application(sender, instance, created, **kwargs):
    """
    Create a conversation when a candidate applies for a vacancy.

    The conversation (and initial Message) is created synchronously to
    guarantee it exists regardless of RQ worker availability. The DB
    writes are lightweight and do not add meaningful latency.
    """
    if not created:
        return

    _create_conversation_sync(instance)


@receiver(post_save, sender=ApplicationDocument)
def create_document_message_on_upload(sender, instance, created, **kwargs):
    """
    Create a document message when an ApplicationDocument is uploaded.

    Runs synchronously because documents are uploaded separately from the
    initial apply request, so the latency is acceptable.
    """
    if not created:
        return

    try:
        application = instance.application

        try:
            conversation = Conversation.objects.get(application=application)
        except Conversation.DoesNotExist:
            logger.warning(
                "No conversation found for application %s when creating "
                "document message for document %s",
                application.id,
                instance.id,
            )
            return

        file_url = instance.file.url if instance.file else None

        message = Message.objects.create(
            conversation=conversation,
            sender_type="CANDIDATE",
            message_type=MessageType.DOCUMENT,
            content=render_default_message(
                "candidate_attached_document", {"title": instance.title}
            ),
            metadata={
                "message_key": "candidate_attached_document",
                "message_params": {"title": instance.title},
                "title": instance.title,
                "file_url": file_url,
                "file_size": instance.file_size,
                "document_type": instance.document_type,
                "document_type_display": instance.get_document_type_display(),
            },
            is_read=False,
        )

        if conversation.is_read_by_recruiter:
            conversation.is_read_by_recruiter = False
            conversation.save(update_fields=["is_read_by_recruiter", "updated_at"])

        broadcast_message(message, conversation=conversation)

        logger.info(
            "Created document message for document %s in conversation %s",
            instance.id,
            conversation.id,
        )

    except Exception:
        logger.error(
            "Failed to create document message for document %s",
            instance.id,
            exc_info=True,
        )
