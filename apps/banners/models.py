from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BannerSlide(models.Model):
    """
    A manually created banner slide shown in the vacancies list carousel.

    The carousel is composed of:
      1. Active BannerSlide rows, ordered by `order`
      2. Auto-generated partner vacancy slides (from companies with has_design=True)

    slide_type controls what layout the frontend renders:
      - VACANCY: pinned vacancy (vacancy FK required)
      - NEWS:    editorial news item
      - AD:      partner advertisement
    """

    class SlideType(models.TextChoices):
        VACANCY = "VACANCY", _("Vacancy")
        NEWS = "NEWS", _("News")
        AD = "AD", _("Advertisement")

    slide_type = models.CharField(
        max_length=10,
        choices=SlideType.choices,
        default=SlideType.NEWS,
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Position in the carousel among manual slides (lower = first)."),
    )
    duration = models.PositiveSmallIntegerField(
        default=3,
        help_text=_("How many seconds this slide stays visible before auto-advancing."),
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(
        null=True, blank=True,
        help_text=_("If set, slide is hidden before this datetime."),
    )
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text=_("If set, slide is hidden after this datetime."),
    )

    # Pinned vacancy (VACANCY type)
    vacancy = models.ForeignKey(
        "vacancies.Vacancy",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="banner_slides",
        help_text=_("Required when slide_type=VACANCY."),
    )

    # Content fields (NEWS / AD)
    title = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    image = models.ImageField(
        upload_to="banner_slides/",
        null=True,
        blank=True,
        help_text=_("Inline content image shown inside the slide body."),
    )
    image_desktop = models.ImageField(
        upload_to="banner_slides/desktop/",
        null=True,
        blank=True,
        help_text=_("Full-cover background image for desktop (≥768 px). NEWS/AD only."),
    )
    image_mobile = models.ImageField(
        upload_to="banner_slides/mobile/",
        null=True,
        blank=True,
        help_text=_("Full-cover background image for mobile (<768 px). Falls back to desktop image if not set."),
    )

    # Language-specific desktop images (override the generic image_desktop per locale)
    image_desktop_uz = models.ImageField(
        upload_to="banner_slides/desktop/uz/",
        null=True,
        blank=True,
        help_text=_("Desktop background image for Uzbek locale. Falls back to image_desktop if not set."),
    )
    image_desktop_ru = models.ImageField(
        upload_to="banner_slides/desktop/ru/",
        null=True,
        blank=True,
        help_text=_("Desktop background image for Russian locale. Falls back to image_desktop if not set."),
    )
    image_desktop_en = models.ImageField(
        upload_to="banner_slides/desktop/en/",
        null=True,
        blank=True,
        help_text=_("Desktop background image for English locale. Falls back to image_desktop if not set."),
    )

    # Language-specific mobile images
    image_mobile_uz = models.ImageField(
        upload_to="banner_slides/mobile/uz/",
        null=True,
        blank=True,
        help_text=_("Mobile background image for Uzbek locale. Falls back to image_mobile if not set."),
    )
    image_mobile_ru = models.ImageField(
        upload_to="banner_slides/mobile/ru/",
        null=True,
        blank=True,
        help_text=_("Mobile background image for Russian locale. Falls back to image_mobile if not set."),
    )
    image_mobile_en = models.ImageField(
        upload_to="banner_slides/mobile/en/",
        null=True,
        blank=True,
        help_text=_("Mobile background image for English locale. Falls back to image_mobile if not set."),
    )

    cta_label = models.CharField(max_length=80, blank=True, default="")
    cta_url = models.CharField(max_length=500, blank=True, default="")

    # Branding (each slide can have its own colors)
    brand_color_from = models.CharField(max_length=7, blank=True, default="", help_text="Hex e.g. #F8EDD9")
    brand_color_to = models.CharField(max_length=7, blank=True, default="", help_text="Hex e.g. #FCE8DA")
    brand_accent_color = models.CharField(max_length=7, blank=True, default="")
    brand_text_color = models.CharField(max_length=7, blank=True, default="")
    brand_border_color = models.CharField(max_length=7, blank=True, default="")

    # HTML banner files — served as static files, rendered via iframe src on the frontend.
    # Use locale-specific fields to override per language; falls back to html_file.
    html_file = models.FileField(
        upload_to="banner_slides/html/",
        null=True, blank=True,
        help_text=_("Upload an .html file. Rendered in a sandboxed iframe. Leave blank to use image/structured layout."),
    )
    html_file_uz = models.FileField(upload_to="banner_slides/html/uz/", null=True, blank=True, help_text=_("HTML file for Uzbek locale. Falls back to html_file."))
    html_file_ru = models.FileField(upload_to="banner_slides/html/ru/", null=True, blank=True, help_text=_("HTML file for Russian locale. Falls back to html_file."))
    html_file_en = models.FileField(upload_to="banner_slides/html/en/", null=True, blank=True, help_text=_("HTML file for English locale. Falls back to html_file."))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Banner Slide")
        verbose_name_plural = _("Banner Slides")
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"[{self.slide_type}] {self.title or self.vacancy or 'untitled'} (order={self.order})"

    @property
    def is_visible(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.expires_at and now > self.expires_at:
            return False
        return True


class BannerClick(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="banner_clicks",
    )
    slide_type = models.CharField(max_length=20)
    vacancy_id = models.UUIDField(null=True, blank=True)
    cta_url = models.CharField(max_length=500, blank=True, default="")
    anon_id = models.CharField(max_length=36, blank=True, default="", help_text="Browser-generated UUID for anonymous user identification")
    clicked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Banner Click")
        verbose_name_plural = _("Banner Clicks")
        ordering = ["-clicked_at"]

    def __str__(self):
        return f"{self.user} clicked {self.slide_type} at {self.clicked_at}"
