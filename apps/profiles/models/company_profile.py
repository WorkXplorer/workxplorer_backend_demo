import io
import os
from django.db import models
from django.core.validators import FileExtensionValidator, RegexValidator
from django.core.files.base import ContentFile
from utils.fields import UUIDField
from utils import AbstractBaseModel


def _compress_image(image_field, max_width=1920, quality=82):
    """Compress an ImageField in-place using Pillow. Skips if already small or non-JPEG/PNG."""
    try:
        from PIL import Image as PILImage
        img_field = image_field
        if not img_field or not img_field.name:
            return
        img_field.open('rb')
        img = PILImage.open(img_field)
        fmt = img.format or 'JPEG'
        # Resize if wider than max_width
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), PILImage.LANCZOS)
        # Convert RGBA → RGB for JPEG (PNG keeps transparency)
        save_fmt = fmt
        if fmt in ('JPEG', 'JPG') and img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        if fmt not in ('JPEG', 'PNG', 'WEBP'):
            save_fmt = 'JPEG'
            img = img.convert('RGB')
        buf = io.BytesIO()
        save_kwargs = {'format': save_fmt, 'optimize': True}
        if save_fmt in ('JPEG', 'WEBP'):
            save_kwargs['quality'] = quality
        img.save(buf, **save_kwargs)
        buf.seek(0)
        ext_map = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}
        name, _ = os.path.splitext(img_field.name)
        new_name = name + ext_map.get(save_fmt, '.jpg')
        img_field.save(new_name, ContentFile(buf.read()), save=False)
    except Exception:
        pass  # Never break a save due to compression failure


class CompanyProfile(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7, editable=False)
    company = models.ForeignKey(
        "authentication.Company",
        on_delete=models.CASCADE,
        related_name="companyprofile",
    )
    photo = models.ImageField(
        upload_to="company_photos/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png"])],
        help_text="Upload a company logo or photo (jpg, jpeg, png formats).",
    )
    description = models.TextField(null=True, blank=True)
    website = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^(https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(:[0-9]{1,5})?(/.*)?$',
                message="Enter a valid website URL or domain (http/https optional).",
                code='invalid_website'
            )
        ],
        help_text="Enter a website URL or domain (http/https optional)."
    )
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.DecimalField(max_digits=30, decimal_places=15, null=True, blank=True)
    longitude = models.DecimalField(max_digits=30, decimal_places=15, null=True, blank=True)

    # PRO partner branding fields
    tagline = models.CharField(max_length=150, null=True, blank=True)
    brand_color_from = models.CharField(max_length=7, null=True, blank=True, help_text="Hex color e.g. #F8EDD9")
    brand_color_to = models.CharField(max_length=7, null=True, blank=True, help_text="Hex color e.g. #FCE8DA")
    brand_accent_color = models.CharField(max_length=7, null=True, blank=True, help_text="Hex color for accents")
    brand_text_color = models.CharField(max_length=7, null=True, blank=True, help_text="Hex color for text on brand bg")
    brand_border_color = models.CharField(max_length=7, null=True, blank=True, help_text="Hex color for borders")
    brand_font = models.CharField(max_length=50, null=True, blank=True, help_text="Google Font name e.g. Caveat")
    brand_font_file = models.FileField(
        upload_to="company_fonts/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["woff", "woff2", "ttf", "otf"])],
        help_text="Upload a custom font file (woff, woff2, ttf, otf). Overrides brand_font if set.",
    )
    brand_name_image = models.ImageField(
        upload_to="company_name_images/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
        help_text="Image of the company wordmark/name to show instead of plain text in the banner.",
    )
    brand_name_image_2 = models.ImageField(
        upload_to="company_name_images/",
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
        help_text="Second brand name image (e.g. full logo with transparent background) for custom branded pages.",
    )
    brand_page_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Slug for custom pages, e.g. 'safia'. Drives dynamic component import on frontend.",
    )
    employees_count = models.PositiveIntegerField(null=True, blank=True)
    locations_count = models.PositiveIntegerField(null=True, blank=True)
    founded_year = models.PositiveIntegerField(null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    reviews_count = models.PositiveIntegerField(null=True, blank=True)
    brand_dark_color = models.CharField(
        max_length=7, null=True, blank=True, help_text="Hex color for title and salary text e.g. #0D1411"
    )
    brand_button_text_color = models.CharField(
        max_length=7, null=True, blank=True, help_text="Hex color for apply button text e.g. #ffffff"
    )

    # Media fields for branded company pages
    video_url = models.URLField(
        max_length=500, null=True, blank=True,
        help_text="URL to a company video (YouTube, Vimeo, or direct link).",
    )
    video_file = models.FileField(
        upload_to="company_videos/",
        null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["mp4", "webm", "mov", "m4v"])],
        help_text="Uploaded company video file (mp4, webm, mov, m4v).",
    )

    def save(self, *args, **kwargs):
        # Compress images before saving to reduce storage and bandwidth
        for field_name in ('photo', 'brand_name_image', 'brand_name_image_2'):
            field = getattr(self, field_name)
            if field and hasattr(field, '_file') and field._file is not None:
                _compress_image(field)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.company.name}"

    class Meta:
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profiles"
        indexes = [
            models.Index(fields=["company"]),
        ]


class CompanyGalleryImage(AbstractBaseModel):
    id = UUIDField(primary_key=True, version=7, editable=False)
    company_profile = models.ForeignKey(
        CompanyProfile,
        on_delete=models.CASCADE,
        related_name="gallery_images",
    )
    image = models.ImageField(
        upload_to="company_gallery/",
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp"])],
        help_text="Gallery image for the branded company page.",
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order (lower = first).")

    def save(self, *args, **kwargs):
        if self.image and hasattr(self.image, '_file') and self.image._file is not None:
            _compress_image(self.image, max_width=1920, quality=80)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Gallery image for {self.company_profile.company.name} (#{self.order})"

    class Meta:
        verbose_name = "Company Gallery Image"
        verbose_name_plural = "Company Gallery Images"
        ordering = ["order"]
