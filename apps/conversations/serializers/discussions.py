from rest_framework import serializers
from ..models import ApplicationDiscussion
from .conversations import RecruiterInfoSerializer
from utils.html_sanitizer import validate_safe_html


class ApplicationDiscussionSerializer(serializers.ModelSerializer):
    recruiter = RecruiterInfoSerializer(read_only=True)

    class Meta:
        model = ApplicationDiscussion
        fields = [
            "id",
            "recruiter",
            "content",
            "is_edited",
            "created_at",
            "status_snapshot",
        ]
        read_only_fields = [
            "id",
            "recruiter",
            "is_edited",
            "created_at",
            "status_snapshot",
        ]

    def validate_content(self, value):
        return validate_safe_html(value)
