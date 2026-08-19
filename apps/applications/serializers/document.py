from rest_framework import serializers
from ..models import ApplicationDocument
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from utils import validate_uploaded_file


class ApplicationDocumentSerializer(serializers.ModelSerializer):
    """
    Serializer for handling document attachments to applications.

    This handles the file uploads and metadata for additional documents
    that candidates might want to include with their applications.
    """

    file_size_display = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationDocument
        fields = [
            "id",
            "document_type",
            "title",
            "file",
            "file_size",
            "file_size_display",
            "created_at",
        ]
        read_only_fields = ["id", "title", "file_size", "created_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_file_size_display(self, obj) -> str:
        """
        Convert file size from bytes to human-readable format.
        """
        if not obj.file_size:
            return "Unknown"

        # Convert bytes to appropriate unit
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def validate_file(self, value):
        return validate_uploaded_file(value)
