from rest_framework import serializers
from .models import Language


class LanguageSerializer(serializers.ModelSerializer):
    """Serializer for listing available languages."""

    class Meta:
        model = Language
        fields = ["id", "name", "code"]
        read_only_fields = ["id"]
