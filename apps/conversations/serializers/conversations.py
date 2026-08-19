import logging
from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.utils import translation

from ..models import Conversation, Message
from apps.authentication.models import Candidate, Recruiter

logger = logging.getLogger(__name__)


class MessageSerializer(serializers.ModelSerializer):
    """
    Serializer for Message model.
    Returns message content and metadata.
    
    For STATUS_CHANGE messages:
    - old_status_display and new_status_display in metadata are dynamically
      translated based on the current request's language.
    - If a default message was used (message_key in metadata), the content
      is also dynamically translated to the viewer's language.
    """

    hunting_status = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender_type",
            "message_type",
            "title",
            "content",
            "metadata",
            "is_read",
            "hunting_status",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from apps.conversations.services import resolve_message_content
        from utils.language import get_request_language

        language = get_request_language()

        # Platform-written messages are stored with a key rather than final
        # text, so each side reads them in their own language. Anything a
        # person typed has no key and is passed through untouched.
        if instance.metadata and instance.metadata.get("message_key"):
            with translation.override(language):
                data["content"] = resolve_message_content(instance)

        if instance.message_type == "STATUS_CHANGE" and instance.metadata:
            from apps.applications.models.choices import ApplicationStatus

            metadata = dict(instance.metadata)
            translations_dict = ApplicationStatus.get_translations()

            # Translate status display names dynamically
            for status_field, display_field in [
                ("old_status", "old_status_display"),
                ("new_status", "new_status_display"),
            ]:
                status_value = metadata.get(status_field)
                if status_value:
                    try:
                        status_obj = ApplicationStatus(status_value)
                        metadata[display_field] = translations_dict[status_obj].get(
                            language, translations_dict[status_obj].get("en", status_value)
                        )
                    except (ValueError, KeyError):
                        logger.warning(f"Unknown status value '{status_value}' in message metadata for message ID {instance.id}")

            # What the AI told the candidate, when the platform rejected them
            # on its own. Attached at read time rather than stored on the
            # message: the summary is written by a background job that runs
            # after this message already exists.
            if metadata.get("changed_by") == "SYSTEM":
                summary = self._ai_rejection_summary(instance, language)
                if summary:
                    metadata["ai_rejection_summary"] = summary

            data["metadata"] = metadata

        return data

    @staticmethod
    def _ai_rejection_summary(instance, language: str) -> str:
        """The AI's own explanation of an auto-rejection, in *language*.

        Written for the candidate — supportive, specific to the vacancy — and
        the same text the vacancy page shows them. Both sides of the chat read
        it, so the recruiter sees exactly what the candidate was told.

        Returns an empty string when there is nothing to show: the roadmap job
        may not have finished yet, or the change may not have been an AI
        rejection at all.
        """
        conversation = instance.conversation
        application = getattr(conversation, "application", None)
        if application is None:
            return ""

        try:
            roadmap = application.vacancy_skill_roadmap
        except ObjectDoesNotExist:
            return ""

        summary = roadmap.rejection_summary or {}
        if not isinstance(summary, dict):
            return ""

        # The generator blanks out any language the model skipped, so a
        # summary can be present in one language and empty in another. Prefer
        # the reader's own, then English, then whatever was actually written:
        # the recruiter reading a rejection in the wrong language still beats
        # a rejection with no explanation at all.
        return (
            summary.get(language)
            or summary.get("en")
            or next((text for text in summary.values() if isinstance(text, str) and text), "")
        )

    def get_hunting_status(self, obj):
        """
        Return True if candidate has applied to the vacancy (for HUNTING_INVITATION messages).
        For other message types, always return False.
        Uses cached value from conversation to avoid N+1 queries.
        """
        # Only check for hunting invitation messages
        if obj.message_type != "HUNTING_INVITATION":
            return False

        # Check if the conversation has cached hunting_status
        # This is set in the view to avoid N+1 queries
        conversation = obj.conversation
        if hasattr(conversation, '_cached_hunting_status'):
            return conversation._cached_hunting_status

        # Fallback: check if application exists for this vacancy
        # This should rarely be hit if views properly set the cache
        if conversation.vacancy_id:
            from apps.applications.models import JobApplication
            return JobApplication.objects.filter(
                candidate_id=conversation.candidate_id,
                vacancy_id=conversation.vacancy_id
            ).exists()

        return False


class CandidateInfoSerializer(serializers.ModelSerializer):
    """
    Minimal candidate info for conversation list.
    Uses prefetched candidateprofile to avoid N+1 queries.
    """

    full_name = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ["id", "full_name", "email", "photo"]
        read_only_fields = fields

    def get_full_name(self, obj):
        # Use prefetched candidateprofile if available
        profile = getattr(obj, 'candidateprofile', None)
        if profile:
            return profile.full_name or obj.email
        return obj.email

    def get_photo(self, obj):
        # Use prefetched candidateprofile if available
        profile = getattr(obj, 'candidateprofile', None)
        if profile and profile.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return None


class RecruiterInfoSerializer(serializers.ModelSerializer):
    """
    Minimal recruiter info for conversation list.
    Uses prefetched recruiterprofile_set to avoid N+1 queries.
    RecruiterProfile uses ForeignKey so we access via recruiterprofile_set.
    """

    full_name = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    company_logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Recruiter
        fields = ["id", "full_name", "email", "photo", "company_name", "company_logo_url"]
        read_only_fields = fields

    def _get_profile(self, obj):
        """
        Get the recruiter profile from prefetched data.
        RecruiterProfile has a ForeignKey to Recruiter, so we access via recruiterprofile_set.
        """
        # Check if prefetched (as list from prefetch_related)
        profile_set = getattr(obj, 'recruiterprofile_set', None)
        if profile_set is not None:
            # If it's a prefetched queryset, check all() cache
            profiles = list(profile_set.all())
            return profiles[0] if profiles else None
        return None

    def get_full_name(self, obj):
        profile = self._get_profile(obj)
        if profile:
            return profile.full_name or obj.email
        return obj.email

    def get_photo(self, obj):
        profile = self._get_profile(obj)
        if profile and profile.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return None

    def get_company_name(self, obj):
        if obj.company:
            return obj.company.name
        return None

    def get_company_logo_url(self, obj):
        """Get company logo URL from CompanyProfile photo field using prefetched data."""
        if obj.company:
            # Use prefetched company profile (set by view with to_attr)
            prefetched_profile = getattr(obj.company, 'prefetched_company_profile', None)
            if prefetched_profile:
                company_profile = prefetched_profile[0] if prefetched_profile else None
                if company_profile and company_profile.photo:
                    request = self.context.get("request")
                    if request:
                        return request.build_absolute_uri(company_profile.photo.url)
                    return company_profile.photo.url
        return None


class ApplicationStatusDisplayMixin:
    """
    Mixin to provide localized application status display names.
    """
    def get_application_status_display(self, obj):
        """
        Return the localized display name of the application status.
        Uses the ApplicationStatus translations with the current request language.
        """
        if not obj.application:
            return None
        from apps.applications.models.choices import ApplicationStatus
        from utils.language import get_request_language
        status_value = obj.application.status
        language = get_request_language()
        translations = ApplicationStatus.get_translations()
        try:
            status_enum = ApplicationStatus(status_value)
            return translations[status_enum].get(language, translations[status_enum].get("uz"))
        except (ValueError, KeyError):
            return obj.application.get_status_display()


class ConversationListSerializer(ApplicationStatusDisplayMixin, serializers.ModelSerializer):
    """
    Serializer for listing conversations.
    Shows basic info and last message preview.
    Uses prefetched recent_messages to avoid N+1 queries.
    """

    candidate = CandidateInfoSerializer(read_only=True)
    recruiter = RecruiterInfoSerializer(read_only=True)
    vacancy_title = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    application_status = serializers.SerializerMethodField()
    application_status_display = serializers.SerializerMethodField()
    conversation_type = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "candidate",
            "recruiter",
            "vacancy_title",
            "last_message_preview",
            "last_message_at",
            "application_status",
            "application_status_display",
            "conversation_type",
            "is_read_by_recruiter",
            "is_read_by_candidate",
            "created_at",
        ]
        read_only_fields = fields

    def get_vacancy_title(self, obj):
        # For application conversations, use application.vacancy
        # For headhunting conversations, use direct vacancy field
        if obj.application:
            return obj.application.vacancy.title
        elif obj.vacancy:
            return obj.vacancy.title
        return None

    def get_application_status(self, obj):
        return obj.application.status if obj.application else None

    def get_conversation_type(self, obj):
        """Return the type of conversation: APPLICATION or HEADHUNTING."""
        return "APPLICATION" if obj.application else "HEADHUNTING"

    def get_last_message_preview(self, obj):
        """Get preview of the last message using prefetched recent_messages."""
        # Use prefetched recent_messages if available
        recent_messages = getattr(obj, 'recent_messages', None)
        if recent_messages:
            last_message = recent_messages[0] if recent_messages else None
        else:
            last_message = obj.messages.order_by("-created_at").first()

        if last_message:
            # Same rule as the thread itself: a platform-written message reads
            # in the viewer's language, so the list and the open conversation
            # never disagree about what the last message said.
            from apps.conversations.services import resolve_message_content
            from utils.language import get_request_language

            with translation.override(get_request_language()):
                content = resolve_message_content(last_message)
            return content[:100] + "..." if len(content) > 100 else content
        return None

    def get_last_message_at(self, obj):
        """Get timestamp of the last message using prefetched recent_messages."""
        # Use prefetched recent_messages if available
        recent_messages = getattr(obj, 'recent_messages', None)
        if recent_messages:
            last_message = recent_messages[0] if recent_messages else None
        else:
            last_message = obj.messages.order_by("-created_at").first()

        dt = last_message.created_at if last_message else obj.created_at
        # SerializerMethodField doesn't automatically go through DateTimeField.to_representation(),
        # so we explicitly use it to ensure proper timezone conversion and formatting
        datetime_field = serializers.DateTimeField()
        return datetime_field.to_representation(dt)

    def to_representation(self, instance):
        """
        Add resume_id to the candidate dict.
        Uses application.resume_used_id which is already loaded via select_related.
        For headhunting conversations or when resume_used is null, uses candidate's
        main or active resume from prefetched data.
        """
        representation = super().to_representation(instance)

        # Try to get resume_id from application first
        resume_id = None
        if instance.application and instance.application.resume_used_id:
            resume_id = instance.application.resume_used_id
        else:
            # For headhunting or when resume_used is null, get from prefetched candidate resumes
            # This is set by the view to avoid N+1 queries
            candidate_resumes = getattr(instance.candidate, 'prefetched_resumes', None)
            if candidate_resumes:
                # Prefer main resume, then any active resume
                main_resume = next((r for r in candidate_resumes if r.is_main and r.is_active), None)
                if not main_resume:
                    main_resume = next((r for r in candidate_resumes if r.is_active), None)
                if main_resume:
                    resume_id = main_resume.id

        # Add resume_id to candidate object
        representation['candidate']['resume_id'] = str(resume_id) if resume_id else None

        return representation


class ConversationDetailSerializer(ApplicationStatusDisplayMixin, serializers.ModelSerializer):
    """
    Serializer for viewing a full conversation with all messages.
    """

    candidate = CandidateInfoSerializer(read_only=True)
    recruiter = RecruiterInfoSerializer(read_only=True)
    vacancy_title = serializers.SerializerMethodField()
    vacancy_id = serializers.SerializerMethodField()
    messages = MessageSerializer(many=True, read_only=True)
    application_status = serializers.SerializerMethodField()
    application_status_display = serializers.SerializerMethodField()
    conversation_type = serializers.SerializerMethodField()
    application_documents = serializers.SerializerMethodField()
    message_quota = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "candidate",
            "recruiter",
            "vacancy_id",
            "vacancy_title",
            "application_status",
            "application_status_display",
            "conversation_type",
            "messages",
            "application_documents",
            "message_quota",
            "is_read_by_recruiter",
            "is_read_by_candidate",
            "created_at",
        ]
        read_only_fields = fields

    def get_vacancy_title(self, obj):
        # For application conversations, use application.vacancy
        # For headhunting conversations, use direct vacancy field
        if obj.application:
            return obj.application.vacancy.title
        elif obj.vacancy:
            return obj.vacancy.title
        return None

    def get_vacancy_id(self, obj):
        # For application conversations, use application.vacancy_id
        # For headhunting conversations, use direct vacancy_id
        if obj.application:
            return obj.application.vacancy_id
        elif obj.vacancy_id:
            return obj.vacancy_id
        return None

    def get_application_status(self, obj):
        return obj.application.status if obj.application else None

    def get_conversation_type(self, obj):
        """Return the type of conversation: APPLICATION or HEADHUNTING."""
        return "APPLICATION" if obj.application else "HEADHUNTING"

    def get_message_quota(self, obj):
        """
        The candidate's remaining message allowance in this conversation.

        Returned only to candidates, because it is only their sending that is
        limited — a recruiter has no budget to display. Lets the composer show
        "3 of 5 left" up front instead of only reporting the limit once the
        candidate is already blocked.
        """
        from apps.conversations.quotas import hourly_status

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_candidate", False):
            return None

        return hourly_status(obj).as_dict()

    def get_application_documents(self, obj):
        """
        Return list of documents attached to the application.
        Uses prefetched documents to avoid N+1 queries.
        """
        if not obj.application:
            return []

        # Try to get prefetched documents
        documents = getattr(obj.application, 'prefetched_documents', None)
        if documents is None:
            documents = obj.application.documents.all()

        request = self.context.get("request")
        result = []
        for doc in documents:
            file_url = None
            if doc.file:
                if request:
                    file_url = request.build_absolute_uri(doc.file.url)
                else:
                    file_url = doc.file.url

            result.append({
                "id": str(doc.id),
                "title": doc.title,
                "file_url": file_url,
                "file_size": doc.file_size,
                "document_type": doc.document_type,
                "document_type_display": doc.get_document_type_display(),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            })

        return result

    def to_representation(self, instance):
        """
        Add resume_id to the candidate dict.
        Uses application.resume_used_id which is already loaded via select_related.
        For headhunting conversations or when resume_used is null, uses candidate's
        main or active resume from prefetched data.
        """
        representation = super().to_representation(instance)

        # Try to get resume_id from application first
        resume_id = None
        if instance.application and instance.application.resume_used_id:
            resume_id = instance.application.resume_used_id
        else:
            # For headhunting or when resume_used is null, get from prefetched candidate resumes
            # This is set by the view to avoid N+1 queries
            candidate_resumes = getattr(instance.candidate, 'prefetched_resumes', None)
            if candidate_resumes:
                # Prefer main resume, then any active resume
                main_resume = next((r for r in candidate_resumes if r.is_main and r.is_active), None)
                if not main_resume:
                    main_resume = next((r for r in candidate_resumes if r.is_active), None)
                if main_resume:
                    resume_id = main_resume.id

        # Add resume_id to candidate object
        representation['candidate']['resume_id'] = str(resume_id) if resume_id else None

        return representation
