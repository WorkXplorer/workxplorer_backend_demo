from django.contrib import admin
from modeltranslation.admin import TranslationAdmin
from import_export import resources
from import_export.fields import Field
from import_export.admin import ExportActionMixin

from .models.edupartner import (
    EduPartnersType,
    EduPartner,
    Faculty,
    Subject,
    SubjectSkill,
)


class EduPartnerTypeAdmin(TranslationAdmin):
    list_display = ("id", "name")

    list_display_links = ("id", "name")

    search_fields = ("id", "name_uz", "name_ru", "name_en")

    list_per_page = 25


class EduPartnerResource(resources.ModelResource):
    id = Field(attribute="id", column_name="ID")
    name = Field(attribute="name", column_name="Name")
    edupartner_type = Field(column_name="Type")
    country = Field(attribute="country", column_name="Country")
    city = Field(attribute="city", column_name="City")
    is_active = Field(attribute="is_active", column_name="Active")
    total_candidates = Field(column_name="Total Candidates")
    active_candidates = Field(column_name="Active Candidates")

    class Meta:
        model = EduPartner
        fields = (
            "id",
            "name",
            "edupartner_type",
            "country",
            "city",
            "is_active",
            "total_candidates",
            "active_candidates",
        )
        export_order = fields

    def dehydrate_edupartner_type(self, obj):
        return obj.edupartner_type.name if obj.edupartner_type_id else ""

    def dehydrate_total_candidates(self, obj):
        return obj.candidates.count()

    def dehydrate_active_candidates(self, obj):
        return obj.candidates.filter(is_active=True).count()


class EduPartnerAdmin(ExportActionMixin, TranslationAdmin):
    resource_classes = [EduPartnerResource]
    list_display = (
        "id",
        "name",
        "edupartner_type",
        "country",
        "city",
        "address",
        "website",
        "logo",
        "description",
        "is_active",
        "created_at",
    )


class FacultyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "edupartner",
        "domain",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "edupartner", "domain")
    search_fields = ("name", "edupartner__name_uz", "edupartner__name_ru", "edupartner__name_en")
    list_per_page = 25


class SubjectSkillInline(admin.TabularInline):
    model = SubjectSkill
    extra = 1
    autocomplete_fields = ["skill"]


class SubjectAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "faculty",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "faculty")
    search_fields = ("name", "faculty__name")
    inlines = [SubjectSkillInline]
    list_per_page = 25


admin.site.register(EduPartnersType, EduPartnerTypeAdmin)
admin.site.register(EduPartner, EduPartnerAdmin)
admin.site.register(Faculty, FacultyAdmin)
admin.site.register(Subject, SubjectAdmin)
