from rest_framework import serializers
from apps.edupartners.models import EduPartnersType, EduPartner, Faculty, Subject
from utils.language import get_request_language


class EduPartnersTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for the EduPartnersType model.
    - Used to represent educational partner types such as University, College, School, etc.
    - Fields: id, name
    """

    name = serializers.SerializerMethodField()

    class Meta:
        model = EduPartnersType
        fields = ["id", "name"]

    def get_name(self, obj):
        language = get_request_language()
        if language == "ru":
            return obj.name_ru or obj.name_en
        elif language == "uz":
            return obj.name_uz or obj.name_en
        return obj.name_en


class EduPartnerSerializer(serializers.ModelSerializer):
    """
    Serializer for the EduPartner model.
    - Includes nested EduPartnersTypeSerializer for better readability.
    - Represents an educational partner with all key details.
    - Logo field returns full URL
    - Name and description are returned according to the selected language.
    """

    # Nested serializer to display full partner type details instead of just the ID
    edupartner_type = EduPartnersTypeSerializer(read_only=True)

    # Custom field to return full logo URL
    logo_url = serializers.SerializerMethodField()

    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = EduPartner
        fields = [
            "id",  # Unique identifier (UUID)
            "name",  # Name of the educational partner
            "edupartner_type",  # Type of partner (University, School, etc.)
            "country",  # Country where the partner is located
            "city",  # City where the partner is located
            "address",  # Full address (optional)
            "website",  # Official website (optional)
            "logo",  # Logo image field (optional)
            "logo_url",  # Full logo URL (custom field)
            "description",  # Additional details/overview (optional)
            "is_active",  # Indicates if the partner is currently active
            "created_at",  # Timestamp of when the partner was created
        ]

    def get_name(self, obj):
        language = get_request_language()
        if language == "ru":
            return obj.name_ru or obj.name_en
        elif language == "uz":
            return obj.name_uz or obj.name_en
        return obj.name_en

    def get_description(self, obj):
        language = get_request_language()
        if language == "ru":
            return obj.description_ru or obj.description_en or ""
        elif language == "uz":
            return obj.description_uz or obj.description_en or ""
        return obj.description_en or ""

    def get_logo_url(self, obj) -> str | None:
        """Return full URL for logo if it exists"""
        if obj.logo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None


class FacultySerializer(serializers.ModelSerializer):
    """
    Serializer for the Faculty model.
    - Represents a faculty within an educational partner.
    """

    edupartner_name = serializers.SerializerMethodField()
    domain_name = serializers.CharField(source="domain.name", read_only=True)

    class Meta:
        model = Faculty
        fields = [
            "id",
            "name",
            "description",
            "edupartner",
            "edupartner_name",
            "domain",
            "domain_name",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_edupartner_name(self, obj):
        language = get_request_language()
        if language == "ru":
            return obj.edupartner.name_ru or obj.edupartner.name_en
        elif language == "uz":
            return obj.edupartner.name_uz or obj.edupartner.name_en
        return obj.edupartner.name_en


class SubjectSerializer(serializers.ModelSerializer):
    """
    Serializer for the Subject model.
    - Represents a subject within a faculty.
    """

    faculty_name = serializers.CharField(source="faculty.name", read_only=True)
    acquired_skills_detail = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "description",
            "faculty",
            "faculty_name",
            "acquired_skills",
            "acquired_skills_detail",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_acquired_skills_detail(self, obj):
        """Return list of skill names"""
        return [
            {"id": str(skill.id), "name": skill.name}
            for skill in obj.acquired_skills.all()
        ]
