"""
Serializers for AI-powered resume generation.
"""

from rest_framework import serializers
from django.utils.translation import gettext as _
from django.core.validators import FileExtensionValidator
from utils.upload_validation import validate_uploaded_file


class ResumeGenerationRequestSerializer(serializers.Serializer):
    """
    Serializer for resume generation request.
    
    Accepts either a prompt text, a file (PDF/DOCX), or both.
    """
    
    prompt = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text=_("Free-form text description or instructions for resume generation."),
    )
    
    file = serializers.FileField(
        required=False,
        help_text=_("Resume file (PDF or DOCX format)."),
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'docx'])
        ],
    )
    
    def validate(self, data):
        """
        Validate that at least one of prompt or file is provided.
        """
        prompt = data.get('prompt', '').strip()
        file = data.get('file')
        
        if not prompt and not file:
            raise serializers.ValidationError(
                _("At least one of 'prompt' or 'file' must be provided."),
                code='required',
            )
        
        # Validate file size (10MB limit) and scan for malware
        if file:
            max_size = 10 * 1024 * 1024  # 10MB
            if file.size > max_size:
                raise serializers.ValidationError(
                    {
                        'file': _(
                            "File size exceeds 10MB limit. Current size: %(size)s MB"
                        ) % {'size': round(file.size / (1024 * 1024), 2)}
                    },
                    code='file_too_large',
                )
            validate_uploaded_file(file)
        
        return data


class CandidateProfileSerializer(serializers.Serializer):
    """Serializer for candidate profile data."""
    full_name = serializers.CharField(allow_null=True)
    email = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    address = serializers.CharField(allow_null=True)
    linkedin = serializers.CharField(allow_null=True)
    github = serializers.CharField(allow_null=True)
    portfolio = serializers.CharField(allow_null=True)


class SkillDataSerializer(serializers.Serializer):
    """Serializer for mapped skill data."""
    skill_id = serializers.IntegerField()
    skill_name = serializers.CharField()
    minimum_years = serializers.IntegerField()
    proficiency_level = serializers.CharField()


class ExperienceDataSerializer(serializers.Serializer):
    """Serializer for experience data."""
    company = serializers.CharField()
    role = serializers.CharField()
    country = serializers.CharField(allow_null=True, required=False)
    city = serializers.CharField(allow_null=True, required=False)
    start_date = serializers.DateField(allow_null=True, required=False)
    end_date = serializers.DateField(allow_null=True, required=False)
    description = serializers.CharField(allow_null=True, required=False)


class CertificateDataSerializer(serializers.Serializer):
    """Serializer for certificate data."""
    name = serializers.CharField(allow_null=True)
    issuing_organization = serializers.CharField(allow_null=True)
    issue_date = serializers.DateField(allow_null=True)
    expiration_date = serializers.DateField(allow_null=True)
    credential_id = serializers.CharField(allow_null=True)
    credential_url = serializers.CharField(allow_null=True)


class LanguageCertificateDataSerializer(serializers.Serializer):
    """Serializer for language certificate data."""
    language_id = serializers.IntegerField()
    language_name = serializers.CharField()
    level = serializers.CharField()


class ResumeDataSerializer(serializers.Serializer):
    """Serializer for generated resume data."""
    description = serializers.CharField()
    position = serializers.CharField()
    domain_id = serializers.IntegerField(allow_null=True, required=False)
    domain_name = serializers.CharField(allow_null=True)
    work_status = serializers.CharField()
    current_company_name = serializers.CharField(allow_null=True)
    current_position = serializers.CharField(allow_null=True)
    employment_start_date = serializers.DateField(allow_null=True)
    current_salary = serializers.DecimalField(max_digits=15, decimal_places=2, allow_null=True)
    salary_currency = serializers.CharField(allow_null=True)
    salary_hide = serializers.BooleanField()
    skills_data = SkillDataSerializer(many=True)
    experiences_data = ExperienceDataSerializer(many=True, required=False)
    certificates_data = CertificateDataSerializer(many=True, required=False)
    language_certificates_data = LanguageCertificateDataSerializer(many=True, required=False)


class MappingMetadataSerializer(serializers.Serializer):
    """Serializer for mapping metadata."""
    skills_matched = serializers.ListField(
        child=serializers.DictField(),
        help_text=_("Successfully matched skills with confidence scores."),
    )
    skills_unmatched = serializers.ListField(
        child=serializers.CharField(),
        help_text=_("Skills that couldn't be matched to database."),
    )
    domain_matched = serializers.DictField(
        allow_null=True,
        help_text=_("Matched domain information."),
    )
    languages_matched = serializers.ListField(
        child=serializers.DictField(),
        help_text=_("Successfully matched languages."),
    )
    languages_unmatched = serializers.ListField(
        child=serializers.CharField(),
        help_text=_("Languages that couldn't be matched to database."),
    )


class ResumeGenerationResponseSerializer(serializers.Serializer):
    """
    Serializer for resume generation response.
    """
    source_type = serializers.CharField()
    detected_language = serializers.CharField()
    candidate_profile = CandidateProfileSerializer()
    resume = ResumeDataSerializer()
    mapping_metadata = MappingMetadataSerializer()


class ResumeGenerationJobStatusSerializer(serializers.Serializer):
    """
    Serializer for job status response.
    """
    job_id = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    result = ResumeGenerationResponseSerializer(required=False, allow_null=True)
    error = serializers.CharField(required=False, allow_null=True)
