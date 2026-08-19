from django.contrib import admin

from apps.hr_templates.models import Template


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "template_type", "application_status", "created_at", "updated_at")
    search_fields = ("title", "description")
    list_filter = ("company", "template_type", "application_status", "created_at")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("application_status",)
    fieldsets = (
        (None, {
            "fields": ("title", "description", "template_type", "company")
        }),
        ("Status Mapping", {
            "fields": ("application_status",),
            "description": "STATUS_CHANGE templates require an application_status. INVITATION templates should leave application_status blank.",
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
