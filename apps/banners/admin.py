from django.contrib import admin
from .models import BannerSlide, BannerClick


@admin.register(BannerSlide)
class BannerSlideAdmin(admin.ModelAdmin):
    list_display = ["__str__", "slide_type", "order", "duration", "is_active", "starts_at", "expires_at"]
    list_filter = ["slide_type", "is_active"]
    list_editable = ["order", "duration", "is_active"]
    ordering = ["order", "created_at"]
    fieldsets = (
        (None, {
            "fields": ("slide_type", "order", "duration", "is_active", "starts_at", "expires_at"),
        }),
        ("Vacancy (VACANCY type)", {
            "fields": ("vacancy",),
            "classes": ("collapse",),
        }),
        ("Content (NEWS / AD)", {
            "fields": (
                "title", "body", "image",
                "image_desktop", "image_mobile",
                "image_desktop_uz", "image_mobile_uz",
                "image_desktop_ru", "image_mobile_ru",
                "image_desktop_en", "image_mobile_en",
                "cta_label", "cta_url",
            ),
            "classes": ("collapse",),
            "description": (
                "image_desktop / image_mobile are the default background images. "
                "Use the language-specific fields (uz/ru/en) to override per locale."
            ),
        }),
        ("HTML Banner", {
            "fields": (
                "html_file",
                "html_file_uz",
                "html_file_ru",
                "html_file_en",
            ),
            "classes": ("collapse",),
            "description": (
                "Upload an .html file per locale. The file is served as a static media file and "
                "rendered in a sandboxed iframe. All clicks are captured by the parent page and "
                "tracked via cta_url (set it above). Scripts in the HTML are allowed."
            ),
        }),
        ("Branding", {
            "fields": ("brand_color_from", "brand_color_to", "brand_accent_color",
                       "brand_text_color", "brand_border_color"),
            "classes": ("collapse",),
        }),
    )


@admin.register(BannerClick)
class BannerClickAdmin(admin.ModelAdmin):
    list_display = ["user", "anon_id", "slide_type", "vacancy_id", "cta_url", "clicked_at"]
    list_filter = ["slide_type"]
    readonly_fields = ["user", "anon_id", "slide_type", "vacancy_id", "cta_url", "clicked_at"]
    ordering = ["-clicked_at"]
