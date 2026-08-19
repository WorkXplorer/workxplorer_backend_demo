from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Avatar,
    DomainMarketSkill,
    EmailTemplate,
    JobQueue,
)


@admin.register(JobQueue)
class JobQueueAdmin(admin.ModelAdmin):
    """Admin interface for JobQueue model with monitoring capabilities."""

    list_display = (
        "id_short",
        "job_type",
        "target_date",
        "target_name",
        "status_badge",
        "retry_count",
        "last_attempt_at",
        "alert_sent",
        "created_at",
    )

    list_filter = (
        "status",
        "job_type",
        "alert_sent",
        "target_date",
    )

    search_fields = (
        "id",
        "target_id",
        "target_name",
        "error_message",
        "rq_job_id",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "payload_hash",
    )

    ordering = ("-created_at",)

    date_hierarchy = "target_date"

    list_per_page = 50

    fieldsets = (
        ("Job Information", {
            "fields": ("id", "job_type", "target_date", "target_id", "target_name")
        }),
        ("Status", {
            "fields": ("status", "retry_count", "max_retries", "last_attempt_at", "alert_sent")
        }),
        ("Error Details", {
            "fields": ("error_message", "rq_job_id"),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("payload_hash", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    actions = ["mark_as_pending", "reset_retry_count", "send_alert"]

    def id_short(self, obj):
        """Display shortened UUID for better readability."""
        return str(obj.id)[:8]

    id_short.short_description = "ID"

    def status_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            "pending": "#FFA500",  # Orange
            "processing": "#007BFF",  # Blue
            "completed": "#28A745",  # Green
            "failed": "#DC3545",  # Red
        }
        color = colors.get(obj.status, "#6C757D")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.status.upper()
        )

    status_badge.short_description = "Status"

    @admin.action(description="Mark selected jobs as pending")
    def mark_as_pending(self, request, queryset):
        """Reset selected jobs to pending status for retry."""
        updated = queryset.update(status=JobQueue.JobStatus.PENDING)
        self.message_user(request, f"{updated} job(s) marked as pending.")

    @admin.action(description="Reset retry count to 0")
    def reset_retry_count(self, request, queryset):
        """Reset retry count for selected jobs."""
        updated = queryset.update(retry_count=0, alert_sent=False)
        self.message_user(request, f"Reset retry count for {updated} job(s).")

    @admin.action(description="Send alert for selected failed jobs")
    def send_alert(self, request, queryset):
        """Manually trigger alert for selected jobs."""
        from apps.general.services.job_queue_service import JobQueueService

        sent_count = 0
        for job in queryset.filter(status=JobQueue.JobStatus.FAILED):
            if JobQueueService.send_alert_for_job(job):
                sent_count += 1

        self.message_user(request, f"Sent {sent_count} alert(s).")


@admin.register(DomainMarketSkill)
class DomainMarketSkillAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "skill_name",
        "domain",
        "query",
        "area_id",
        "vacancy_count",
        "is_active",
        "last_seen_at",
        "expires_at",
    )
    list_filter = ("source", "area_id", "is_active", "language", "last_seen_at")
    search_fields = (
        "skill_name",
        "normalized_skill_name",
        "query",
        "normalized_query",
        "scope_key",
    )
    readonly_fields = ("created_at", "updated_at", "first_seen_at", "last_seen_at")
    ordering = ("-vacancy_count", "skill_name")


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    # Columns to display in the list view
    list_display = ("id", "name", "template_type", "language", "subject")

    # Fields that can be searched in the admin panel
    search_fields = ("name", "subject", "template_type")

    # Filters available in the sidebar
    list_filter = ("language", "template_type")

    # Default ordering for the list view
    ordering = ("name",)

    # Fields that will be read-only
    readonly_fields = ("id",)

    # Field grouping in the detail view
    fieldsets = (
        (None, {"fields": ("name", "template_type", "language", "subject", "body")}),
    )


admin.site.register(Avatar)
