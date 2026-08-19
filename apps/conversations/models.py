from django.db import models
from django.utils.translation import gettext_lazy as _
from utils.abstract_model import AbstractBaseModel
from utils.fields import UUIDField


class Conversation(AbstractBaseModel):
    """
    Represents a conversation between a candidate and a recruiter.
    
    This can be created:
    1. Automatically when a candidate applies for a vacancy (has application)
    2. By a recruiter when headhunting a candidate (no application)
    
    The conversation is private between the candidate and the recruiter.
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this conversation"),
    )

    application = models.OneToOneField(
        "applications.JobApplication",
        on_delete=models.CASCADE,
        related_name="conversation",
        null=True,
        blank=True,
        help_text=_("The job application this conversation is about (null for headhunting)"),
    )

    candidate = models.ForeignKey(
        "authentication.Candidate",
        on_delete=models.CASCADE,
        related_name="conversations",
        help_text=_("The candidate participating in this conversation"),
    )

    recruiter = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.CASCADE,
        related_name="conversations",
        help_text=_("The recruiter participating in this conversation"),
    )

    vacancy = models.ForeignKey(
        "vacancies.Vacancy",
        on_delete=models.SET_NULL,
        related_name="headhunting_conversations",
        null=True,
        blank=True,
        help_text=_("The vacancy this headhunting invitation is for (null for application conversations)"),
    )

    is_read_by_recruiter = models.BooleanField(
        default=False,
        help_text=_("Whether the recruiter has read the messages"),
    )

    is_read_by_candidate = models.BooleanField(
        default=False,
        help_text=_("Whether the candidate has read the messages"),
    )

    class Meta:
        verbose_name = _("Conversation")
        verbose_name_plural = _("Conversations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["candidate", "recruiter"]),
            models.Index(fields=["recruiter", "-created_at"]),
            models.Index(fields=["candidate", "-created_at"]),
            # Speeds up headhunting conversation lookup in signals.py
            models.Index(
                fields=["candidate", "recruiter", "vacancy"],
                name="conv_headhunting_lookup_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "recruiter", "application"],
                name="unique_application_conversation",
                condition=models.Q(application__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["candidate", "recruiter"],
                name="unique_headhunting_conversation",
                condition=models.Q(application__isnull=True),
            ),
            models.CheckConstraint(
                condition=(
                        models.Q(application__isnull=True, vacancy__isnull=False) |  # Headhunting with vacancy
                        models.Q(application__isnull=True, vacancy__isnull=True) |  # Headhunting without vacancy
                        models.Q(application__isnull=False, vacancy__isnull=True)
                # Application (vacancy from application)
                ),
                name="check_application_vacancy_exclusivity",
                violation_error_message="Application conversations cannot have a direct vacancy. Use application.vacancy instead.",
            ),
        ]

    def __str__(self):
        if self.application_id:
            return f"Conversation for Application {self.application_id}"
        return f"Headhunting: {self.recruiter.email} -> {self.candidate.email}"


class MessageType(models.TextChoices):
    """Types of messages that can be sent in a conversation."""
    COVER_LETTER = "COVER_LETTER", _("Cover Letter")
    TEXT = "TEXT", _("Text Message")
    SYSTEM = "SYSTEM", _("System Message")
    STATUS_CHANGE = "STATUS_CHANGE", _("Status Change")
    DOCUMENT = "DOCUMENT", _("Document")
    HUNTING_INVITATION = "HUNTING_INVITATION", _("Headhunting Invitation")


class Message(AbstractBaseModel):
    """
    Represents a single message in a conversation.
    
    Initially, this will only contain the cover letter from the candidate's
    application. In the future, this can be extended to support
    real-time messaging between candidates and recruiters.
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this message"),
    )

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        help_text=_("The conversation this message belongs to"),
    )

    sender_type = models.CharField(
        max_length=20,
        choices=[
            ("CANDIDATE", _("Candidate")),
            ("RECRUITER", _("Recruiter")),
            ("SYSTEM", _("System")),
        ],
        help_text=_("Type of the sender"),
    )

    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.COVER_LETTER,
        help_text=_("Type of the message"),
    )

    content = models.TextField(
        help_text=_("The message content"),
    )

    title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Optional title for the message (e.g., recruiter note title for status changes)"),
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Additional structured data for special message types. "
            "For STATUS_CHANGE: {old_status, new_status, old_status_display, new_status_display, recruiter_note}. "
            "For DOCUMENT: {title, file_url, file_size, document_type}."
        ),
    )

    is_read = models.BooleanField(
        default=False,
        help_text=_("Whether the message has been read by the recipient"),
    )

    class Meta:
        verbose_name = _("Message")
        verbose_name_plural = _("Messages")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(
                fields=["conversation", "is_read", "sender_type"],
                name="message_unread_sender_idx",
            ),
        ]

    def __str__(self):
        return f"Message in {self.conversation_id} from {self.sender_type}"


class ApplicationDiscussion(AbstractBaseModel):
    """
    Internal discussion among company recruiters about an application/candidate.
    
    This allows recruiters within the same company to leave comments about a
    specific job application, visible only to other recruiters in the company.
    Not visible to candidates.
    """

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text=_("Unique identifier for this discussion"),
    )

    application = models.ForeignKey(
        "applications.JobApplication",
        on_delete=models.CASCADE,
        related_name="internal_discussions",
        help_text=_("The job application this discussion is about"),
    )

    recruiter = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.CASCADE,
        related_name="internal_discussions",
        help_text=_("The recruiter who wrote this discussion"),
    )

    content = models.TextField(
        help_text=_("The discussion message content"),
    )

    is_edited = models.BooleanField(
        default=False,
        help_text=_("Whether this discussion has been edited"),
    )

    status_snapshot = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text=_("Application status key at the time this discussion was created"),
    )

    class Meta:
        verbose_name = _("Application Discussion")
        verbose_name_plural = _("Application Discussions")
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["application", "created_at"],
                name="discussion_app_created_idx",
            ),
        ]

    def __str__(self):
        return f"Discussion by {self.recruiter_id} on application {self.application_id}"
