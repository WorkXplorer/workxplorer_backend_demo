# utils/serializers_mixins.py
from rest_framework import serializers
from django.core.files.uploadedfile import UploadedFile

# Register HEIC/HEIF support for Pillow
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass  # pillow-heif not installed, HEIC format won't be supported


class FlexibleImageField(serializers.ImageField):
    """
    A flexible ImageField that accepts either:
    - an uploaded file (UploadedFile, InMemoryUploadedFile, TemporaryUploadedFile)
    - or an existing image path / URL (string)
    """

    def to_internal_value(self, data):
        # Case 1: File upload
        if isinstance(data, UploadedFile):
            from utils.upload_validation import validate_uploaded_file
            
            # 1. Run antivirus check on the uploaded file first
            #    This ensures malicious files get a "Virus detected" error
            #    instead of a generic "Invalid image" error from Pillow.
            validate_uploaded_file(data)
            
            # 2. Allow SVG files directly (Pillow does not support SVG)
            #    If you want to validate SVG structure, you can add it here.
            file_name = data.name.lower() if data.name else ""
            if file_name.endswith(".svg") or getattr(data, 'content_type', '') == 'image/svg+xml':
                return data

            # 3. For all other images, pass to DRF ImageField which uses Pillow
            return super().to_internal_value(data)

        # Case 2: String (existing path or URL)
        if isinstance(data, str):
            # Treat string "null" or "None" as None to properly delete the photo
            if data.lower() in ('null', 'none', ''):
                return None
            return data

        # Case 3: None or empty
        if data in [None, ""]:
            return None

        raise serializers.ValidationError(
            "Photo must be an image file or a string path."
        )

    def to_representation(self, value):
        """Custom representation to handle None values properly"""
        if not value:
            return None

        # If it's a string path, check for empty/null values
        if isinstance(value, str):
            if value in ('', 'null', 'None'):
                return None
            return value

        # Handle ImageFieldFile (when there's an actual file)
        # Check if the file actually has a name/path
        if hasattr(value, 'name') and (not value.name or value.name in ('null', 'None', '')):
            return None

        if hasattr(value, 'url'):
            # Try to get request from context safely
            request = None
            if hasattr(self, 'context') and self.context:
                request = self.context.get('request')
            elif hasattr(self, 'parent') and hasattr(self.parent, 'context') and self.parent.context:
                request = self.parent.context.get('request')

            if request:
                return request.build_absolute_uri(value.url)
            return value.url

        return None
