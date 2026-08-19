from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    """Inline for viewing messages within a conversation."""
    model = Message
    extra = 0
    readonly_fields = ["id", "sender_type", "message_type", "content", "is_read", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Admin configuration for Conversation model."""

    list_display = [
        "id",
        "get_candidate_name",
        "get_recruiter_name",
        "get_vacancy_title",
        "is_read_by_recruiter",
        "is_read_by_candidate",
        "created_at",
    ]
    list_filter = ["is_read_by_recruiter", "is_read_by_candidate", "created_at"]
    search_fields = [
        "candidate__email",
        "recruiter__email",
        "application__vacancy__title",
    ]
    readonly_fields = ["id", "application", "candidate", "recruiter", "created_at", "updated_at"]
    inlines = [MessageInline]
    list_select_related = ["candidate", "recruiter", "application__vacancy"]

    def get_candidate_name(self, obj):
        return f"{obj.candidate.email}"

    get_candidate_name.short_description = "Candidate"

    def get_recruiter_name(self, obj):
        return f"{obj.recruiter.email}"

    get_recruiter_name.short_description = "Recruiter"

    def get_vacancy_title(self, obj):
        return obj.application.vacancy.title if obj.application else "Headhunting"

    get_vacancy_title.short_description = "Vacancy"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin configuration for Message model."""

    list_display = [
        "id",
        "get_conversation_id",
        "sender_type",
        "message_type",
        "get_content_preview",
        "is_read",
        "created_at",
    ]
    list_filter = ["sender_type", "message_type", "is_read", "created_at"]
    search_fields = ["content", "conversation__candidate__email", "conversation__recruiter__email"]
    readonly_fields = ["id", "conversation", "created_at", "updated_at"]

    def get_conversation_id(self, obj):
        return str(obj.conversation_id)[:8] + "..."

    get_conversation_id.short_description = "Conversation"

    def get_content_preview(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content

    get_content_preview.short_description = "Content"
