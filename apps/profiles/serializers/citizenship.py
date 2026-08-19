from rest_framework import serializers

from utils.language import get_request_language

from ..models import Citizenship


class CitizenshipSerializer(serializers.ModelSerializer):
    """
    Serializer for Citizenship model with multilingual support.
    Returns the name in the requested language (en, ru, uz).
    """

    name = serializers.SerializerMethodField()

    class Meta:
        model = Citizenship
        fields = ("id", "name")
        read_only_fields = ("id",)

    def get_name(self, obj) -> str:
        """Return citizenship name in the requested language."""
        language = get_request_language()
        if language == "ru":
            return obj.name_ru or obj.name_en or obj.name
        elif language == "uz":
            return obj.name_uz or obj.name_en or obj.name
        return obj.name_en or obj.name
