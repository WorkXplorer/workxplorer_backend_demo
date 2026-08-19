from rest_framework import serializers
from apps.profiles.models import CandidateProfile


class StudentSerializer(serializers.ModelSerializer):
    """
    Serializer for the Student model.
    - Represents a student within an educational partner.
    """
    date_joined = serializers.DateTimeField(source="candidate.date_joined", read_only=True)
    is_active = serializers.BooleanField(source="candidate.is_active", read_only=True)
    faculty = serializers.CharField(source="candidate.faculty.name", read_only=True)
    status = serializers.CharField(read_only=True)


    class Meta:
        model = CandidateProfile
        fields = [
            "id",
            "photo",
            "status",
            "faculty",
            "full_name",
            "is_active",
            "created_at",
            "updated_at",
            "date_joined",
        ]
