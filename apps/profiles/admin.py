from django.contrib import admin
from django.utils.timezone import now
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
from import_export import resources
from import_export.fields import Field
from import_export.admin import ExportActionMixin
from modeltranslation.admin import TranslationAdmin

from .models import CandidateProfile, Citizenship, CompanyProfile, CompanyGalleryImage


class CandidateProfileResource(resources.ModelResource):
    id = Field(attribute='id', column_name='ID')
    full_name = Field(attribute='full_name', column_name='Full Name')
    candidate_email = Field(attribute='candidate_email', column_name='Profile Email')
    phone = Field(attribute='phone', column_name='Phone')
    address = Field(attribute='address', column_name='Address')
    region = Field(attribute='region', column_name='Region')

    class Meta:
        model = CandidateProfile
        fields = ('id', 'full_name', 'candidate_email', 'phone', 'address', 'region')
        export_order = ('id', 'full_name', 'candidate_email', 'phone', 'address', 'region')


class DateJoinedFilter(admin.SimpleListFilter):
    title = _("Date Joined")
    parameter_name = "date_joined"

    def lookups(self, request, model_admin):
        return (
            ("today", _("Today")),
            ("week", _("Last 7 days")),
            ("month", _("Last 30 days")),
        )

    def queryset(self, request, queryset):
        today = now().date()
        if self.value() == "today":
            return queryset.filter(candidate__date_joined__date=today)
        elif self.value() == "week":
            return queryset.filter(
                candidate__date_joined__gte=now() - timedelta(days=7)
            )
        elif self.value() == "month":
            return queryset.filter(
                candidate__date_joined__gte=now() - timedelta(days=30)
            )
        return queryset


class CandidateProfileAdmin(ExportActionMixin, admin.ModelAdmin):
    resource_classes = [CandidateProfileResource]
    list_display = (
        "id",
        "candidate",
        "full_name",
        "photo",
        "date_joined",
    )
    list_display_links = ("id", "candidate", "full_name")
    search_fields = ("candidate__email", "full_name")
    list_filter = (DateJoinedFilter, "citizenship")
    list_per_page = 25
    ordering = ("-candidate__date_joined",)

    def date_joined(self, obj):
        return obj.candidate.date_joined

    date_joined.short_description = _("Date Joined")


class CitizenshipAdmin(TranslationAdmin):
    list_display = ("id", "name", "name_en", "name_ru", "name_uz", "created_at")
    list_display_links = ("id", "name")
    search_fields = ("name", "name_en", "name_ru", "name_uz")
    list_per_page = 25
    ordering = ("name",)


class CompanyGalleryImageInline(admin.TabularInline):
    model = CompanyGalleryImage
    extra = 1
    fields = ("image", "order")


class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "created_at", "website")
    list_display_links = ("id", "company")
    search_fields = ("company__name", "description", "address", "website")
    list_per_page = 25
    ordering = ("-created_at",)
    inlines = [CompanyGalleryImageInline]
    fieldsets = (
        (None, {
            "fields": ("company", "photo", "description", "address", "website", "phone_number",
                       "latitude", "longitude"),
        }),
        ("PRO Branding", {
            "fields": ("tagline", "brand_color_from", "brand_color_to",
                       "brand_accent_color", "brand_text_color", "brand_border_color", "brand_dark_color",
                       "brand_font", "brand_font_file", "brand_name_image", "brand_name_image_2", "brand_button_text_color",
                       "brand_page_type", "employees_count", "locations_count",
                       "founded_year", "rating", "reviews_count"),
            "classes": ("collapse",),
        }),
        ("Media", {
            "fields": ("video_url", "video_file"),
            "classes": ("collapse",),
        }),
    )


admin.site.register(CandidateProfile, CandidateProfileAdmin)
admin.site.register(Citizenship, CitizenshipAdmin)
admin.site.register(CompanyProfile, CompanyProfileAdmin)
