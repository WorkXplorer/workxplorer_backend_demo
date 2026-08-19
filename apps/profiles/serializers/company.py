from rest_framework import serializers
from django.conf import settings
from django.utils.translation import gettext as _
from ..models import CompanyProfile, CompanyGalleryImage
from apps.authentication.models import Recruiter
from apps.domain.models import Domain
from utils import FlexibleImageField, validate_uploaded_file


class DomainSerializer(serializers.ModelSerializer):
    """Serializer for Domain model"""

    class Meta:
        model = Domain
        fields = ("id", "name", "description")


class AboutCompanySerializer(serializers.ModelSerializer):
    """
    Complete serializer for About Company functionality.
    Combines Company and CompanyProfile data.
    """

    photo = FlexibleImageField(required=False, allow_null=True)

    # Company fields
    company_name = serializers.CharField(source='company.name', read_only=True)
    company_tin = serializers.CharField(source='company.tin', read_only=True)
    company_domain = serializers.SerializerMethodField()
    company_email = serializers.SerializerMethodField()
    company_phone_number = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = CompanyProfile
        fields = (
            "photo", "description", "address", "website",
            "company_name", "company_tin", "company_domain",
            "company_email", "company_phone_number", "created_at",
            "latitude", "longitude",
            "tagline",
            "brand_color_from", "brand_color_to",
            "brand_accent_color", "brand_text_color", "brand_border_color",
            "brand_font",
        )
        read_only_fields = ("id", "company", "company_name", "company_tin",
                            "company_domain", "company_email", "created_at")

    def get_company_domain(self, obj):
        """Return company domain as a list"""
        if obj.company and obj.company.domain:
            return [DomainSerializer(obj.company.domain).data]
        return []

    def get_company_email(self, obj):
        """Get email from the first recruiter of the company"""
        if not hasattr(obj, '_first_recruiter') or obj._first_recruiter is None:
            # Fallback if prefetch wasn't used
            first_recruiter = Recruiter.objects.filter(
                company=obj.company
            ).order_by('date_joined').first()
            return first_recruiter.email if first_recruiter else None
        return obj._first_recruiter.email

    def validate_photo(self, value):
        """Validate photo field"""
        if value is None:
            # Only raise error if we're trying to delete a photo that doesn't exist
            # and the request is explicitly for deletion
            # For regular None values, just return None
            return value

        validate_uploaded_file(value, allow_string=True)

        if value and hasattr(value, 'size'):
            if value.size > settings.MAX_FILE_SIZE:
                raise serializers.ValidationError(
                    _("Photo size should not exceed %(limit)sMB")
                    % {"limit": settings.MAX_FILE_SIZE // (1024 * 1024)}
                )
        return value

    def to_representation(self, instance):
        """Custom representation to populate company_phone_number from recruiter profile"""
        data = super().to_representation(instance)

        # Get company_phone_number from first recruiter's profile
        if not hasattr(instance, '_first_recruiter') or instance._first_recruiter is None:
            from apps.profiles.models import RecruiterProfile
            first_recruiter = Recruiter.objects.filter(
                company=instance.company
            ).order_by('date_joined').first()
            if first_recruiter:
                profile = RecruiterProfile.objects.filter(recruiter=first_recruiter).first()
                data['company_phone_number'] = profile.phone if profile else None
            else:
                data['company_phone_number'] = None
        else:
            # Use cached profile if available
            if hasattr(instance._first_recruiter, '_recruiter_profile'):
                data['company_phone_number'] = instance._first_recruiter._recruiter_profile.phone
            else:
                # Query for it
                from apps.profiles.models import RecruiterProfile
                profile = RecruiterProfile.objects.filter(recruiter=instance._first_recruiter).first()
                data['company_phone_number'] = profile.phone if profile else None

        return data

    def update(self, instance, validated_data):  # type: ignore[override]
        """Update company profile"""
        # Handle photo field
        if "photo" in validated_data:
            photo = validated_data.get("photo")
            if photo is None:
                # Delete the existing photo file and set field to None
                if instance.photo:
                    instance.photo.delete(save=False)
                instance.photo = None
            elif isinstance(photo, str):
                # Check if it's a "null" string that should delete the photo
                if photo.lower() in ('null', 'none', ''):
                    if instance.photo:
                        instance.photo.delete(save=False)
                    instance.photo = None
                else:
                    # Valid path, keep it
                    instance.photo = photo
                validated_data.pop("photo")

        # Handle company_phone_number field - update the first recruiter's profile
        if "company_phone_number" in validated_data:
            phone_number = validated_data.pop("company_phone_number")
            from apps.profiles.models import RecruiterProfile

            # Get the first recruiter of the company
            first_recruiter = Recruiter.objects.filter(
                company=instance.company
            ).order_by('date_joined').first()

            if first_recruiter:
                # Get or create the recruiter's profile
                profile, created = RecruiterProfile.objects.get_or_create(
                    recruiter=first_recruiter,
                    defaults={'phone': phone_number}
                )
                if not created:
                    profile.phone = phone_number
                    profile.save()

        return super().update(instance, validated_data)


class CompanyGalleryImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CompanyGalleryImage
        fields = ('id', 'image_url', 'order')

    def get_image_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.image:
            return request.build_absolute_uri(obj.image.url) if request else obj.image.url
        return None


class CompanyPublicDetailSerializer(serializers.ModelSerializer):
    """Public company detail serializer for branded company pages."""

    company_id = serializers.UUIDField(source='company.id', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    photo_url = serializers.SerializerMethodField()
    brand_name_image_url = serializers.SerializerMethodField()
    brand_name_image_2_url = serializers.SerializerMethodField()
    brand_font_file_url = serializers.SerializerMethodField()
    video_file_url = serializers.SerializerMethodField()
    gallery_images = serializers.SerializerMethodField()

    class Meta:
        model = CompanyProfile
        fields = (
            'company_id',
            'company_name',
            'photo_url',
            'brand_name_image_url',
            'brand_name_image_2_url',
            'brand_font_file_url',
            'description',
            'address',
            'website',
            'tagline',
            'brand_color_from',
            'brand_color_to',
            'brand_accent_color',
            'brand_text_color',
            'brand_border_color',
            'brand_dark_color',
            'brand_button_text_color',
            'brand_font',
            'brand_page_type',
            'employees_count',
            'locations_count',
            'founded_year',
            'rating',
            'reviews_count',
            'video_url',
            'video_file_url',
            'gallery_images',
        )

    def get_photo_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.photo:
            return request.build_absolute_uri(obj.photo.url) if request else obj.photo.url
        return None

    def get_brand_name_image_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.brand_name_image:
            return request.build_absolute_uri(obj.brand_name_image.url) if request else obj.brand_name_image.url
        return None

    def get_brand_name_image_2_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.brand_name_image_2:
            return request.build_absolute_uri(obj.brand_name_image_2.url) if request else obj.brand_name_image_2.url
        return None

    def get_brand_font_file_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.brand_font_file:
            return request.build_absolute_uri(obj.brand_font_file.url) if request else obj.brand_font_file.url
        return None

    def get_video_file_url(self, obj) -> str | None:
        request = self.context.get('request')
        if obj.video_file:
            return request.build_absolute_uri(obj.video_file.url) if request else obj.video_file.url
        return None

    def get_gallery_images(self, obj) -> list:
        images = obj.gallery_images.all()
        request = self.context.get('request')
        return [
            request.build_absolute_uri(img.image.url) if request else img.image.url
            for img in images if img.image
        ]
