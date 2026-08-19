import logging
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from .models import Conversation, Message, MessageType
from .realtime import broadcast_message

logger = logging.getLogger(__name__)


# Default message keys for candidate actions (used for dynamic translation)
DEFAULT_MESSAGE_KEYS = {
    "OFFER_ACCEPTED": "candidate_accepted_offer",
    "OFFER_REJECTED": "candidate_rejected_offer",
    "WITHDRAWN": "candidate_withdrawn_application",
}

# Default messages mapped by key (translatable)
#
# A message stored under one of these keys is written by the platform rather
# than by a person, so it is rendered in the language of whoever is *reading*
# it — the recruiter should not be shown the candidate's Uzbek because the
# candidate happened to be the one who triggered it.
DEFAULT_MESSAGES = {
    "candidate_accepted_offer": _("The candidate has accepted the offer"),
    "candidate_rejected_offer": _("The candidate has rejected the offer"),
    "candidate_withdrawn_application": _("The candidate has withdrawn the application"),
    "candidate_applied_to_vacancy": _(
        "Candidate has applied to the vacancy: %(vacancy_title)s"
    ),
    "candidate_attached_document": _("Attached document: %(title)s"),
}


def render_default_message(message_key: str, params: dict | None = None) -> str:
    """Render ``message_key`` in the currently active language.

    Values the sentence needs (a vacancy title, a file name) are stored beside
    the key as ``message_params`` rather than baked into the text, so the
    sentence around them can be swapped per reader.
    """
    template = DEFAULT_MESSAGES.get(message_key)
    if template is None:
        return ""

    text = str(template)
    if not params:
        return text

    try:
        return text % params
    except (KeyError, ValueError, TypeError):
        # A translation with a mistyped placeholder must not blank out the
        # message; the untouched template still says what happened.
        logger.warning(
            "Could not interpolate default message '%s' with params %s",
            message_key, sorted(params),
        )
        return text


def resolve_message_content(message) -> str:
    """Return what *message* should read as in the active language.

    Falls back to the stored ``content``, which is what messages people
    actually typed — and what platform messages written before they carried a
    key still hold.
    """
    metadata = message.metadata or {}
    message_key = metadata.get("message_key")
    if message_key and message_key in DEFAULT_MESSAGES:
        rendered = render_default_message(message_key, metadata.get("message_params"))
        if rendered:
            return rendered
    return message.content


def create_status_change_message(
        application,
        old_status: str,
        new_status: str,
        recruiter_note: str = None,
        changed_by: str = "RECRUITER",
        title: str = None,
        candidate_message: str = None,
) -> Message | None:
    """
    Create a status change message in the conversation for a job application.
    
    This function creates a message that records:
    - The old and new status values with localized display names
    - When the change occurred
    - Any recruiter note associated with the change
    - An optional title for the recruiter note
    - An optional candidate message (cover letter) for offer accept/reject
    
    The sender_type logic:
    - RECRUITER: when a recruiter changes status AND provides a note
    - SYSTEM: when a recruiter changes status WITHOUT a note, or a system
      action (e.g. AI auto-reject)
    - CANDIDATE: when a candidate initiates the change (regardless of whether 
      they provide a custom message)
    
    Status display names are localized based on the current language context.
    
    When a candidate accepts/rejects an offer:
    - If candidate_message is provided, it is used as the message content
    - If not, a default translatable message is stored, with a message_key
      in metadata so the message can be dynamically translated per viewer's language
    
    Args:
        application: JobApplication instance
        old_status: The previous status value (e.g., "APPLIED")
        new_status: The new status value (e.g., "INTERVIEW_SCHEDULED")
        recruiter_note: Optional note from the recruiter explaining the change
        changed_by: Who initiated the change ("RECRUITER" or "CANDIDATE")
        title: Optional title for the recruiter note message
        candidate_message: Optional message from candidate (e.g., cover letter for offer response)

    Returns:
        Message instance if created successfully, None otherwise
    """
    from apps.applications.models import ApplicationStatus

    try:
        # Get the conversation for this application
        conversation = getattr(application, 'conversation', None)
        if not conversation:
            # Try to fetch it if not loaded
            try:
                conversation = Conversation.objects.get(application=application)
            except Conversation.DoesNotExist:
                logger.warning(
                    f"No conversation found for application {application.id}. "
                    "Status change message will not be created."
                )
                return None

        timestamp = timezone.now()

        # Get current language for localized status displays
        language = translation.get_language() or 'en'
        
        # Get localized status display names
        translations_dict = ApplicationStatus.get_translations()
        
        try:
            old_status_obj = ApplicationStatus(old_status)
            old_status_display = translations_dict[old_status_obj].get(
                language, translations_dict[old_status_obj].get('en', old_status)
            )
        except (ValueError, KeyError):
            old_status_display = old_status

        try:
            new_status_obj = ApplicationStatus(new_status)
            new_status_display = translations_dict[new_status_obj].get(
                language, translations_dict[new_status_obj].get('en', new_status)
            )
        except (ValueError, KeyError):
            new_status_display = new_status

        # Determine content and sender_type
        message_key = None
        if changed_by == "RECRUITER":
            content = recruiter_note or ""
            sender_type = "RECRUITER" if recruiter_note else "SYSTEM"
        elif changed_by == "CANDIDATE":
            # Candidate action - always set sender_type as CANDIDATE
            sender_type = "CANDIDATE"
            if candidate_message:
                content = candidate_message
            else:
                # Use a default translatable message
                message_key = DEFAULT_MESSAGE_KEYS.get(new_status)
                if message_key and message_key in DEFAULT_MESSAGES:
                    content = str(DEFAULT_MESSAGES[message_key])
                else:
                    content = ""
        else:
            # System action (e.g. AI auto-reject) - treat as SYSTEM sender
            content = ""
            sender_type = "SYSTEM"

        # Build metadata
        metadata = {
            "old_status": old_status,
            "new_status": new_status,
            "old_status_display": old_status_display,
            "new_status_display": new_status_display,
            "recruiter_note": recruiter_note or "",
            "changed_by": changed_by,
            "changed_at": timestamp.isoformat(),
        }
        if message_key:
            metadata["message_key"] = message_key

        # Create the message with structured metadata
        message = Message.objects.create(
            conversation=conversation,
            sender_type=sender_type,
            message_type=MessageType.STATUS_CHANGE,
            content=content,
            title=title,
            metadata=metadata,
            is_read=False,
        )

        # Mark conversation as unread for the other party
        if changed_by == "RECRUITER":
            conversation.is_read_by_candidate = False
            conversation.save(update_fields=["is_read_by_candidate", "updated_at"])
        else:
            conversation.is_read_by_recruiter = False
            conversation.save(update_fields=["is_read_by_recruiter", "updated_at"])

        logger.info(
            f"Created status change message {message.id} for application {application.id}: "
            f"{old_status} -> {new_status}"
        )

        # Push it to whichever participant has the chat open. Best effort:
        # the message is already committed, so a gateway outage costs a
        # refresh, not a message.
        broadcast_message(message, conversation=conversation)

        return message

    except Exception as e:
        logger.error(
            f"Failed to create status change message for application {application.id}: {e}",
            exc_info=True,
        )
        return None
