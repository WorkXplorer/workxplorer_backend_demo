import re

from rest_framework import serializers

from utils import FlexibleImageField
from utils.language import get_request_language

from ..models import CandidateProfile, Citizenship
from apps.edupartners.models import EduPartner, Faculty
from apps.authentication.models import Candidate
from django.utils.translation import gettext as _
from utils import validate_uploaded_file


class CandidateProfileSerializer(serializers.ModelSerializer):
    photo = FlexibleImageField(required=False, allow_null=True)
    is_vault_verified = serializers.BooleanField(
        source="candidate.is_vault_verified",
        read_only=True
    )
    edupartner_id = serializers.UUIDField(
        required=False,
        allow_null=True,
    )
    faculty_id = serializers.UUIDField(
        required=False,
        allow_null=True,
    )
    citizenship_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="UUID of the citizenship to assign",
    )
    citizenship_name = serializers.SerializerMethodField()
    email = serializers.EmailField(
        source="candidate.email",
        read_only=True
    )
    date_of_birth = serializers.DateField(
        source="candidate.date_of_birth",
        required=False,
        allow_null=True,
        help_text="Date of birth in YYYY-MM-DD format (stored on Candidate model)",
    )

    class Meta:
        model = CandidateProfile
        fields = (
            "id",
            "email",
            "is_vault_verified",
            "phone",
            "full_name",
            "photo",
            "address",
            "education",
            "edupartner_id",
            "faculty_id",
            "date_of_birth",
            "citizenship_id",
            "citizenship_name",
            "github_url",
            "linkedin_url",
            "social_url",
            "telegram_url",
        )

    def get_citizenship_name(self, obj) -> str | None:
        """Return citizenship name in the requested language."""
        if not obj.citizenship:
            return None
        language = get_request_language()
        if language == "ru":
            return obj.citizenship.name_ru or obj.citizenship.name_en or obj.citizenship.name
        elif language == "uz":
            return obj.citizenship.name_uz or obj.citizenship.name_en or obj.citizenship.name
        return obj.citizenship.name_en or obj.citizenship.name
    
    def to_representation(self, instance):
        """Override to include the candidate's edupartner_id and faculty_id"""
        data = super().to_representation(instance)
        if instance.candidate:
            data['edupartner_id'] = instance.candidate.edupartner_id
            data['faculty_id'] = instance.candidate.faculty_id
        return data

    def validate_telegram_url(self, value):
        if not value:
            return value
        value = value.strip()
        value = re.sub(r'^@', '', value)
        value = re.sub(r'^https?://(www\.)?t\.me/', '', value)
        value = re.sub(r'^(www\.)?t\.me/', '', value)
        value = value.rstrip('/')
        return f'https://t.me/{value}'

    def validate_photo(self, value):
        return validate_uploaded_file(value, allow_string=True)

    def _validate_citizenship(self, citizenship_id):
        """Validate and return the Citizenship object."""
        if not citizenship_id:
            return None
        try:
            return Citizenship.objects.get(id=citizenship_id)
        except Citizenship.DoesNotExist:
            raise serializers.ValidationError(
                {"citizenship_id": str(_("Citizenship with this ID does not exist"))}
            )

    def _build_education_json(self, edupartner_name: str) -> dict:
        """Build education JSON structure with edupartner name."""
        return {
            "course": "",
            "faculty": "",
            "speciality": "",
            "university": edupartner_name,
        }

    def create(self, validated_data):
        user = self.context['request'].user
        if not hasattr(user, "is_candidate") or not user.is_candidate:
                raise serializers.ValidationError(
                    {"email": str(_("Authenticated user is not a candidate"))}
                )

        # Try to get the candidate by their registration email
        try:
            candidate = Candidate.objects.get(email=user.email)
        except Candidate.DoesNotExist:
                raise serializers.ValidationError(
                    {"email": str(_("No candidate found with this email"))}
                )

        # Check if this candidate already has a profile
        if CandidateProfile.objects.filter(candidate=candidate).exists():
                raise serializers.ValidationError(
                    {"email": str(_("Profile already exists for this candidate"))}
                )

        # Handle date_of_birth (stored on Candidate model)
        candidate_data = validated_data.pop('candidate', {})
        if 'date_of_birth' in candidate_data:
            candidate.date_of_birth = candidate_data['date_of_birth']

        # Handle citizenship_id
        citizenship_id = validated_data.pop('citizenship_id', None)
        citizenship = self._validate_citizenship(citizenship_id)
        if citizenship:
            validated_data['citizenship'] = citizenship

        # Handle edupartner_id
        edupartner_id = validated_data.pop('edupartner_id', None)
        edupartner = None
        if edupartner_id:
            try:
                edupartner = EduPartner.objects.get(id=edupartner_id)
            except EduPartner.DoesNotExist:
                raise serializers.ValidationError(
                    {"edupartner_id": str(_("EduPartner with this ID does not exist"))}
                )
            candidate.edupartner_id = edupartner_id
            # Set education JSON with edupartner name if not already provided
            if not validated_data.get('education'):
                validated_data['education'] = self._build_education_json(edupartner.name)

        # Handle faculty_id
        faculty_id = validated_data.pop('faculty_id', None)
        if faculty_id:
            try:
                faculty = Faculty.objects.get(id=faculty_id)
                # Validate that faculty belongs to selected edupartner
                if candidate.edupartner_id and faculty.edupartner_id != candidate.edupartner_id:
                    raise serializers.ValidationError(
                        {"faculty_id": str(_("Faculty does not belong to selected EduPartner"))}
                    )
            except Faculty.DoesNotExist:
                raise serializers.ValidationError(
                    {"faculty_id": str(_("Faculty with this ID does not exist"))}
                )
            candidate.faculty_id = faculty_id
        
        candidate.save()

        # Assign the candidate and create the profile
        validated_data["candidate"] = candidate
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Handle date_of_birth (stored on Candidate model)
        candidate_data = validated_data.pop('candidate', {})
        if 'date_of_birth' in candidate_data:
            instance.candidate.date_of_birth = candidate_data['date_of_birth']
            instance.candidate.save(update_fields=['date_of_birth'])

        # Handle citizenship_id
        if 'citizenship_id' in validated_data:
            citizenship_id = validated_data.pop('citizenship_id')
            if citizenship_id:
                citizenship = self._validate_citizenship(citizenship_id)
                validated_data['citizenship'] = citizenship
            else:
                validated_data['citizenship'] = None

        # Handle edupartner_id
        if 'edupartner_id' in validated_data:
            edupartner_id = validated_data.pop('edupartner_id')
            if edupartner_id:
                try:
                    EduPartner.objects.get(id=edupartner_id)
                except EduPartner.DoesNotExist:
                    raise serializers.ValidationError(
                        {"edupartner_id": str(_("EduPartner with this ID does not exist"))}
                    )
                instance.candidate.edupartner_id = edupartner_id
            else:
                instance.candidate.edupartner_id = None
            instance.candidate.save()

        # Handle faculty_id
        if 'faculty_id' in validated_data:
            faculty_id = validated_data.pop('faculty_id')
            if faculty_id:
                try:
                    faculty = Faculty.objects.get(id=faculty_id)
                    # Validate that faculty belongs to selected edupartner
                    if instance.candidate.edupartner_id and faculty.edupartner_id != instance.candidate.edupartner_id:
                        raise serializers.ValidationError(
                            {"faculty_id": str(_("Faculty does not belong to selected EduPartner"))}
                        )
                except Faculty.DoesNotExist:
                    raise serializers.ValidationError(
                        {"faculty_id": str(_("Faculty with this ID does not exist"))}
                    )
                instance.candidate.faculty_id = faculty_id
            else:
                instance.candidate.faculty_id = None
            instance.candidate.save()

        # Handle photo field carefully
        if 'photo' in validated_data:
            photo = validated_data['photo']

            if photo is None:
                # Photo explicitly sent as None/empty - delete existing photo
                if instance.photo:
                    # Delete old photo file from storage
                    instance.photo.delete(save=False)
                validated_data['photo'] = None
            elif isinstance(photo, str):
                # If a string path, assign directly (existing photo URL)
                instance.photo = photo
                validated_data.pop('photo')
            # else: photo is a file upload, let it process normally
        # If 'photo' not in validated_data, keep existing photo (no change)

        return super().update(instance, validated_data)
