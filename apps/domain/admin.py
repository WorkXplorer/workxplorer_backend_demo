from modeltranslation.admin import TranslationAdmin
from import_export import resources
from import_export.fields import Field
from django.contrib import admin
from .models import Domain
from import_export.admin import ImportExportModelAdmin, ExportActionMixin

class DomainResource(resources.ModelResource):
    id = Field(attribute='id', column_name='ID')
    name_en = Field(attribute='name_en', column_name='English')
    name_ru = Field(attribute='name_ru', column_name='Русский')
    name_uz = Field(attribute='name_uz', column_name='O\'zbekcha')
    description_en = Field(attribute='description_en', column_name='Description English')
    description_ru = Field(attribute='description_ru', column_name='Описание Русский')
    description_uz = Field(attribute='description_uz', column_name="Tavsif O'zbekcha")

    class Meta:
        model = Domain
        fields = ('id', 'name_en', 'name_ru', 'name_uz', 'description_en', 'description_ru', 'description_uz',)
        import_id_fields = ('id',)
        skip_unchanged = True
        report_skipped = True


@admin.register(Domain)
class DomainAdmin(TranslationAdmin, ImportExportModelAdmin, ExportActionMixin):
    """
    Admin interface for Domain model with full CRUD functionality.
    """
    resource_classes = [DomainResource]
    list_display = ["name", "created_at", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["name", "description"]
    ordering = ["name"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        ("Basic Information", {"fields": ("name", "description")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    actions = ["duplicate_domains"]
    def duplicate_domains(self, request, queryset):
        """Custom action to duplicate selected domains."""
        count = 0
        for domain in queryset:
            domain.pk = None
            domain.name = f"{domain.name} (Copy)"
            domain.save()
            count += 1

        self.message_user(request, f"{count} domain(s) successfully duplicated.")

    duplicate_domains.short_description = "Duplicate selected domains"
