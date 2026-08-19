import json
import logging
from datetime import date as date_type

from rest_framework import serializers
from django.utils.translation import gettext as _
from django.core.files.storage import default_storage
from ..models import (
    Resume,
    ResumeSkill,
    ResumeExperience,
    ResumeCertificate,
    ResumeLanguageCertificate,
)
from ..models.choices import ProficiencyLevel, LanguageProficiencyLevel, WorkStatus
from apps.skills.models import Skill
from apps.skills.localization import localized_skill_name, user_preferred_language
from apps.domain.models import Domain
from apps.languages.models import Language
from utils.parse_date import parse_date
from utils.language import get_request_language
from utils.upload_validation import validate_uploaded_file
from utils.fields.certificate import MAX_FILE_SIZE, ALLOWED_EXTENSIONS
from ..services import CertificateService
from ..services.experience import calculate_total_experience_months, format_experience

logger = logging.getLogger(__name__)

# Maximum number of skills a single resume may contain.
MAX_RESUME_SKILLS = 25


def has_skill_name(resume_skill):
    return bool(localized_skill_name(resume_skill.skill))


class ResumeCertificateSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying resume certificates.
    Includes certificate_image_url for file access with full URL.
    """

    certificate_image_url = serializers.SerializerMethodField()

    class Meta:
        model = ResumeCertificate
        fields = [
            "id",
            "name",
            "issuing_organization",
            "issue_date",
            "expiration_date",
            "credential_id",
            "credential_url",
            "certificate_image_url",
        ]

    def get_certificate_image_url(self, obj) -> str | None:
        """Return full URL for certificate file if it exists"""
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class ResumeLanguageCertificateSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying language certificates on a resume.
    Includes language details, proficiency level, and file URL.
    """

    language_id = serializers.IntegerField(source="language.id", read_only=True)
    language_name = serializers.CharField(source="language.name", read_only=True)
    language_code = serializers.CharField(source="language.code", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ResumeLanguageCertificate
        fields = [
            "id",
            "language_id",
            "language_name",
            "language_code",
            "level",
            "file_url",
        ]

    def get_file_url(self, obj) -> str | None:
        """Return full URL for language certificate file if it exists."""
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class ResumeSkillSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying resume skills in responses.
    Similar to VacancySkillSerializer.
    """

    skill_name = serializers.SerializerMethodField()
    skill_id = serializers.IntegerField(source="skill.id", read_only=True)
    is_pending = serializers.SerializerMethodField()
    warning = serializers.SerializerMethodField()

    class Meta:
        model = ResumeSkill
        fields = [
            "skill_id",
            "skill_name",
            "minimum_years",
            "proficiency_level",
            "is_pending",
            "warning",
        ]

    def get_skill_name(self, obj):
        request = self.context.get("request")
        return localized_skill_name(
            obj.skill,
            user_preferred_language(getattr(request, "user", None)),
        )

    def get_is_pending(self, obj):
        """A skill is pending while it has not yet been AI-approved."""
        return not obj.skill.is_active

    def get_warning(self, obj):
        """
        Human-readable warning shown for not-yet-approved skills. The frontend
        decides how to style it; ``None`` means the skill is approved.
        """
        if obj.skill.is_active:
            return None
        return _("This skill has not been approved yet and is pending review.")


class ResumeExperienceSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying resume experiences.
    Duration is calculated dynamically from start_date and end_date.
    """

    duration = serializers.SerializerMethodField()

    class Meta:
        model = ResumeExperience
        fields = [
            "company",
            "role",
            "country",
            "city",
            "start_date",
            "end_date",
            "description",
            "duration",
        ]

    def get_duration(self, obj) -> str:
        """Calculate duration from start_date and end_date."""
        if not obj.start_date:
            return format_experience(0)
        end = obj.end_date or date_type.today()
        # Use inclusive month calculation: add 1 to end month for proper counting
        total_months = (end.year - obj.start_date.year) * 12 + (end.month - obj.start_date.month) + 1
        total_months = max(total_months, 0)
        return format_experience(total_months)


class JSONStringField(serializers.Field):
    """
    Custom field that handles both JSON strings and parsed JSON objects.
    Useful for FormData submissions where JSON is sent as strings.
    """

    def to_internal_value(self, data):
        if data is None or data == "":
            return []

        # If it's already a list/dict, return as is
        if isinstance(data, (list, dict)):
            return data

        # If it's a string, try to parse it
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return parsed
            except json.JSONDecodeError:
                raise serializers.ValidationError(_("Invalid JSON format."))

        raise serializers.ValidationError(_("Expected a JSON string or object."))

    def to_representation(self, value):
        return value


class ResumeSerializer(serializers.ModelSerializer):
    """
    Serializer for Resume model with skill, experience, and certificate support.
    Follows the same pattern as VacancySerializer.
    """

    # Read-only fields for displaying resume data
    resume_skills = serializers.SerializerMethodField()
    experiences = ResumeExperienceSerializer(many=True, read_only=True)
    certificates = ResumeCertificateSerializer(many=True, read_only=False, required=False, allow_empty=True)
    language_certificates = ResumeLanguageCertificateSerializer(many=True, read_only=True)

    # Domain information
    domain = serializers.PrimaryKeyRelatedField(
        queryset=Domain.objects.all(),
        required=False,
        allow_null=True,
        help_text="Domain ID for the resume's professional field",
    )
    domain_name = serializers.CharField(source="domain.name", read_only=True)

    # Candidate full name from CandidateProfile
    candidate_full_name = serializers.SerializerMethodField()

    # Candidate region from CandidateProfile
    candidate_region = serializers.SerializerMethodField()

    # Candidate image URL from CandidateProfile
    candidate_img_url = serializers.SerializerMethodField()

    # Candidate email
    candidate_email = serializers.SerializerMethodField()

    # Candidate phone number from CandidateProfile
    candidate_phone_number = serializers.SerializerMethodField()

    # Candidate address from CandidateProfile
    candidate_address = serializers.SerializerMethodField()

    # Candidate edupartner name
    candidate_edupartner_name = serializers.SerializerMethodField()

    # Candidate date of birth from CandidateProfile
    candidate_date_of_birth = serializers.SerializerMethodField()

    # Candidate citizenship from CandidateProfile (language-aware)
    candidate_citizenship = serializers.SerializerMethodField()

    # Candidate edupartner faculty from education JSON
    candidate_edupartner_faculty = serializers.SerializerMethodField()

    # Candidate edupartner course from education JSON
    candidate_edupartner_course = serializers.SerializerMethodField()

    # Total experience calculated dynamically
    total_experience = serializers.SerializerMethodField()

    # Work status display with translation
    work_status_display = serializers.SerializerMethodField()

    # Conversation ID between the requesting HR/recruiter and the candidate
    conversation_id = serializers.SerializerMethodField()

    # Make title optional
    title = serializers.CharField(max_length=140, required=False, allow_blank=True)

    # Write-only fields using custom JSONStringField
    skills_data = JSONStringField(
        write_only=True,
        required=False,
        help_text="List of skills with proficiency details.",
    )

    experiences_data = JSONStringField(
        write_only=True,
        required=False,
        help_text="List of work experiences.",
    )

    certificates_data = JSONStringField(
        write_only=True,
        required=False,
        help_text="List of certificates.",
    )

    language_certificates_data = JSONStringField(
        write_only=True,
        required=False,
        help_text="List of language certificates: [{language_id, level, file?}]",
    )

    class Meta:
        model = Resume
        fields = (
            "id",
            "title",
            "description",
            "position",
            "domain",
            "domain_name",
            "work_status",
            "work_status_display",
            "is_main",
            "candidate_full_name",
            "candidate_img_url",
            "candidate_region",
            "candidate_email",
            "candidate_phone_number",
            "candidate_address",
            "candidate_edupartner_name",
            "candidate_date_of_birth",
            "candidate_citizenship",
            "candidate_edupartner_faculty",
            "candidate_edupartner_course",
            "current_salary",
            "salary_currency",
            "salary_hide",
            "resume_skills",
            "skills_data",
            "experiences",
            "experiences_data",
            "certificates",
            "certificates_data",
            "language_certificates",
            "language_certificates_data",
            "total_experience",
            "conversation_id",
            "created_at",
            "created_by_type",
            "is_embedded",
            "is_reviewed",
        )
        read_only_fields = (
            "id",
            "created_at",
            "domain_name",
            "is_main",
            "is_embedded",
            "candidate_full_name",
            "candidate_img_url",
            "candidate_region",
            "candidate_email",
            "candidate_phone_number",
            "candidate_address",
            "candidate_edupartner_name",
            "candidate_date_of_birth",
            "candidate_citizenship",
            "candidate_edupartner_faculty",
            "candidate_edupartner_course",
            "total_experience",
            "work_status_display",
            "conversation_id",
            "created_by_type",
        )

    def get_candidate_profile(self, obj):
        """Get the candidate profile from the related Candidate object."""
        try:
            return obj.candidate.candidateprofile
        except (AttributeError, Exception):
            # CandidateProfile.DoesNotExist or candidate is None
            return None

    def get_candidate_full_name(self, obj) -> str:
        profile = self.get_candidate_profile(obj)
        return profile.full_name if profile else (obj.candidate.email if obj.candidate else None)

    def get_resume_skills(self, obj):
        resume_skills = [
            resume_skill
            for resume_skill in obj.resume_skills.all()
            if has_skill_name(resume_skill)
        ]
        return ResumeSkillSerializer(
            resume_skills,
            many=True,
            context=self.context,
        ).data

    def get_candidate_region(self, obj) -> str:
        profile = self.get_candidate_profile(obj)
        return profile.region if profile else ""

    def get_candidate_img_url(self, obj):
        profile = self.get_candidate_profile(obj)
        if profile and profile.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return None

    def get_candidate_email(self, obj) -> str:
        """Return candidate's email address."""
        return obj.candidate.email if obj.candidate else ""

    def get_candidate_phone_number(self, obj) -> str:
        """Return candidate's phone number from profile."""
        profile = self.get_candidate_profile(obj)
        return profile.phone if profile and profile.phone else ""

    def get_candidate_address(self, obj) -> str:
        """Return candidate's address from profile."""
        profile = self.get_candidate_profile(obj)
        return profile.address if profile and profile.address else ""

    def get_candidate_edupartner_name(self, obj) -> str:
        """Return candidate's educational partner name."""
        if not obj.candidate or not obj.candidate.edupartner:
            return ""
        
        return obj.candidate.edupartner.name

    def get_candidate_date_of_birth(self, obj) -> str | None:
        """Return candidate's date of birth from Candidate model."""
        if obj.candidate and obj.candidate.date_of_birth:
            return str(obj.candidate.date_of_birth)
        return None

    def get_candidate_citizenship(self, obj) -> str | None:
        """Return candidate's citizenship name in the requested language."""
        profile = self.get_candidate_profile(obj)
        if not profile or not profile.citizenship:
            return None
        
        language = get_request_language()
        citizenship = profile.citizenship
        if language == "ru":
            return citizenship.name_ru or citizenship.name_en or citizenship.name
        elif language == "uz":
            return citizenship.name_uz or citizenship.name_en or citizenship.name
        return citizenship.name_en or citizenship.name

    def get_candidate_edupartner_faculty(self, obj) -> str | None:
        """Return candidate's faculty from education JSON field."""
        profile = self.get_candidate_profile(obj)
        if not profile or not profile.education:
            return None
        
        try:
            education_data = profile.education if isinstance(profile.education, dict) else json.loads(profile.education)
            return education_data.get("faculty")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    def get_candidate_edupartner_course(self, obj) -> str | None:
        """Return candidate's course from education JSON field."""
        profile = self.get_candidate_profile(obj)
        if not profile or not profile.education:
            return None
        
        try:
            education_data = profile.education if isinstance(profile.education, dict) else json.loads(profile.education)
            return education_data.get("course")
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None

    def get_total_experience(self, obj) -> str:
        """Calculate total experience from all resume experiences, handling overlaps."""
        experiences = getattr(obj, 'prefetched_experiences', None)
        if experiences is None:
            experiences = obj.experiences.all()
        intervals = []
        for exp in experiences:
            if exp.start_date:
                intervals.append((exp.start_date, exp.end_date))
        total_months = calculate_total_experience_months(intervals)
        return format_experience(total_months)

    def get_work_status_display(self, obj) -> str:
        """Return translated work status display based on request language."""
        if not obj.work_status:
            return ""
        
        # Get language from Django's translation framework (set by LocaleMiddleware)
        language = get_request_language()
        
        # Get translations for the work status
        translations = WorkStatus.get_translations()
        
        # Find the matching work status enum
        try:
            work_status_enum = WorkStatus(obj.work_status)
            if work_status_enum in translations:
                return translations[work_status_enum].get(language, translations[work_status_enum]['en'])
        except (ValueError, KeyError):
            logger.warning(f"Work status value '{obj.work_status}' is not a valid WorkStatus enum.")
        
        # Fallback to the raw value if translation not found
        return obj.work_status

    def get_conversation_id(self, obj):
        """
        Return the conversation ID between the requesting HR/recruiter and the candidate.
        
        Returns:
            - str: UUID of the conversation if it exists
            - None: If no conversation exists or user is not a recruiter
        
        Optimization Note:
        This method performs a single query per resume detail request.
        For list views with multiple resumes, consider prefetching conversations
        in the view's get_queryset() method to avoid N+1 queries.
        """
        from apps.conversations.models import Conversation
        
        # Get the request from context
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return None
        
        user = request.user
        
        # Only return conversation_id for recruiters
        if not getattr(user, 'is_recruiter', False):
            return None
        
        # Query for a conversation between this recruiter and the resume's candidate
        # Use only() to fetch only the ID field for efficiency
        conversation = (
            Conversation.objects
            .filter(
                candidate_id=obj.candidate_id,
                recruiter_id=user.id
            )
            .only('id')
            .first()
        )
        
        return str(conversation.id) if conversation else None

    @staticmethod
    def _lookup_domain_by_name(domain_name):
        """
        Look up a domain by name across all language variants (en, ru, uz).
        Raises ValidationError if no matching domain is found.
        """
        from django.db.models import Q

        # Try case-insensitive match on all translated name fields
        domain = Domain.objects.filter(
            Q(name__iexact=domain_name)
            | Q(name_en__iexact=domain_name)
            | Q(name_ru__iexact=domain_name)
            | Q(name_uz__iexact=domain_name)
        ).first()

        if domain:
            return domain

        raise serializers.ValidationError(
            {"domain_name": _("Domain with this name does not exist.")}
        )

    def validate(self, data):
        """
        Handle domain lookup by name if domain wasn't provided by ID.
        Supports both: {"domain": 5} and {"domain_name": "IT"}.
        Priority: domain ID takes precedence over domain_name.
        """
        request_data = self.initial_data
        domain_name = (
            request_data.get("domain_name", "").strip()
            if request_data.get("domain_name")
            else ""
        )
        domain_value = data.get("domain") or request_data.get("domain")

        if data.get("domain"):
            return data

        # Check if domain field is empty or not provided
        # Handle various empty representations: None, "", "null", empty after strip
        if not domain_value or str(domain_value).strip() in ("", "null", "None"):
            if domain_name:
                domain = self._lookup_domain_by_name(domain_name)
                data["domain"] = domain
            elif self.instance is None or "domain" in request_data:
                raise serializers.ValidationError(
                    {"domain": _("Domain is required.")}
                )

        return data

    def validate_skills_data(self, value):
        """
        Validate the skills data format and ensure skills exist.
        """
        if not value:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(_("Expected a list of skill objects."))

        if len(value) > MAX_RESUME_SKILLS:
            raise serializers.ValidationError(
                _("A resume can have at most %(limit)d skills.")
                % {"limit": MAX_RESUME_SKILLS}
            )

        validated_skills = []
        seen_skill_ids = set()

        for skill_data in value:
            if not isinstance(skill_data, dict):
                raise serializers.ValidationError(_("Each skill must be a dictionary."))

            if "skill_id" not in skill_data:
                raise serializers.ValidationError(
                    _("Each skill must have a 'skill_id' field.")
                )

            skill_id = skill_data["skill_id"]
            if skill_id in seen_skill_ids:
                raise serializers.ValidationError(
                    _("Skill with ID {skill_id} is listed more than once.").format(
                        skill_id=skill_id
                    )
                )
            seen_skill_ids.add(skill_id)

            try:
                skill = Skill.objects.get(id=skill_data["skill_id"])
            except Skill.DoesNotExist:
                raise serializers.ValidationError(
                    _("Skill with ID {skill_id} does not exist.").format(
                        skill_id=skill_data["skill_id"]
                    )
                )

            if not localized_skill_name(skill):
                raise serializers.ValidationError(
                    _("Skill with ID {skill_id} has an empty name.").format(
                        skill_id=skill_data["skill_id"]
                    )
                )

            proficiency_level = skill_data.get(
                "proficiency_level", ProficiencyLevel.UNDEFINED
            )
            valid_levels = [choice[0] for choice in ProficiencyLevel.choices]
            if proficiency_level not in valid_levels:
                raise serializers.ValidationError(
                    _("Invalid proficiency_level.")
                )

            minimum_years = skill_data.get("minimum_years", 0)
            if not isinstance(minimum_years, int) or minimum_years < 0:
                minimum_years = 0

            validated_skills.append(
                {
                    "skill": skill,
                    "minimum_years": minimum_years,
                    "proficiency_level": proficiency_level,
                }
            )

        return validated_skills

    def validate_experiences_data(self, value):
        """Validate experiences data format with proper date parsing."""
        import datetime
        from django.utils import timezone

        if not value:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(_("Expected a list of experience objects."))

        validated_experiences = []
        for idx, exp_data in enumerate(value):
            if not isinstance(exp_data, dict):
                raise serializers.ValidationError(
                    "Each experience must be a dictionary."
                )

            company = exp_data.get("company", "").strip() if exp_data.get("company") else ""
            if not company:
                raise serializers.ValidationError(
                    f"Company name is required for experience at index {idx}."
                )

            start_date_raw = exp_data.get("start_date")
            end_date_raw = exp_data.get("end_date")

            if not start_date_raw:
                raise serializers.ValidationError(
                    f"Start date is required for experience at index {idx}."
                )

            try:
                start_date = datetime.datetime.strptime(
                    start_date_raw, "%Y-%m-%d"
                ).date()

            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f"Start date must be in YYYY-MM-DD format at index {idx}."
                )
            end_date = None
            if end_date_raw:
                try:
                    end_date = datetime.datetime.strptime(
                        end_date_raw, "%Y-%m-%d"
                    ).date()
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"End date must be in YYYY-MM-DD format at index {idx}."
                    )

            today = timezone.now().date()
            if start_date > today or (end_date and end_date > today):
                raise serializers.ValidationError(
                    f"Start date and/or end date cannot be in the future at index {idx}."
                )

            # Parse dates with proper handling of strings and empty values
            start_date = parse_date(start_date_raw)
            end_date = parse_date(end_date_raw)

            # Validate date logic: end_date should not be before start_date
            if start_date and end_date and end_date < start_date:
                raise serializers.ValidationError(
                    f"End date cannot be before start date for experience at index {idx}."
                )

            validated_experiences.append(
                {
                    "company": company,
                    "role": exp_data.get("role", "").strip() if exp_data.get("role") else "",
                    "country": exp_data.get("country", "").strip() if exp_data.get("country") else "",
                    "city": exp_data.get("city", "").strip() if exp_data.get("city") else "",
                    "start_date": start_date,
                    "end_date": end_date,
                    "description": exp_data.get("description", "").strip() if exp_data.get("description") else "",
                }
            )

        return validated_experiences

    def validate_certificates_data(self, value):
        """Validate certificates data using the CertificateService."""
        if not value:
            return []

        # Use the service for validation but don't pass resume yet (it doesn't exist in validation)
        validated_certificates, _ = CertificateService.validate_certificates_data(value)
        return validated_certificates

    def validate_language_certificates_data(self, value):
        """
        Validate language certificates data.

        Each entry must have:
        - language_id (int, required): ID of the Language
        - level (str, required): CEFR level (A1-C2)
        - file (optional): Certificate file

        Validates:
        - No duplicate languages within the same request
        - Language exists in the database
        - Level is a valid CEFR level
        - File size and format constraints
        """
        if not value:
            return []

        if not isinstance(value, list):
            raise serializers.ValidationError(
                _("Expected a list of language certificate objects.")
            )

        valid_levels = [choice[0] for choice in LanguageProficiencyLevel.choices]
        seen_language_ids = set()
        validated = []

        # Collect all language IDs first (N+1 query optimization)
        language_ids = []
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    _("Each language certificate must be a dictionary at index %(idx)s.")
                    % {"idx": idx}
                )

            language_id = item.get("language_id")
            if not language_id:
                raise serializers.ValidationError(
                    _("'language_id' is required for language certificate at index %(idx)s.")
                    % {"idx": idx}
                )
            
            # Convert to int if it's a string (from form-data)
            try:
                language_id = int(language_id)
                item["language_id"] = language_id  # Update the item with the int value
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    _("'language_id' must be a valid integer at index %(idx)s.")
                    % {"idx": idx}
                )
            
            language_ids.append(language_id)

        # Fetch all languages in one query
        languages_map = Language.objects.in_bulk(language_ids)

        for idx, item in enumerate(value):
            language_id = item.get("language_id")

            # Check for duplicates within the request
            if language_id in seen_language_ids:
                raise serializers.ValidationError(
                    _("Duplicate language certificate: language_id %(language_id)s appears more than once.")
                    % {"language_id": language_id}
                )
            seen_language_ids.add(language_id)

            # Validate language exists using the pre-fetched map
            language = languages_map.get(language_id)
            if not language:
                raise serializers.ValidationError(
                    _("Language with ID %(language_id)s does not exist.")
                    % {"language_id": language_id}
                )

            level = item.get("level", "").strip()
            if not level or level not in valid_levels:
                raise serializers.ValidationError(
                    _("Invalid proficiency level '%(level)s' at index %(idx)s. Valid levels: %(valid)s")
                    % {"level": level, "idx": idx, "valid": ", ".join(valid_levels)}
                )

            file_obj = item.get("file")
            
            # Validate file size and format
            if hasattr(file_obj, "size"):
                validate_uploaded_file(file_obj, allow_string=True)
                if file_obj.size > MAX_FILE_SIZE:
                    raise serializers.ValidationError(
                        _("File '%(name)s' exceeds 5MB limit at index %(idx)s.")
                        % {"name": file_obj.name, "idx": idx}
                    )
                file_name = file_obj.name.lower()
                extension = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
                if extension not in ALLOWED_EXTENSIONS:
                    raise serializers.ValidationError(
                        _("File '%(name)s' has invalid type at index %(idx)s. Allowed: %(allowed)s")
                        % {"name": file_obj.name, "idx": idx, "allowed": ", ".join(ALLOWED_EXTENSIONS)}
                    )

            # Handle id field for updates (convert to int if it's a string)
            item_id = item.get("id")
            if item_id:
                try:
                    item_id = int(item_id)
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        _("'id' must be a valid integer at index %(idx)s.")
                        % {"idx": idx}
                    )
            
            validated.append({
                "id": item_id,
                "language": language,
                "level": level,
                "file": file_obj,
            })

        return validated

    def create(self, validated_data):
        """
        Create resume and associated skills, experiences, certificates,
        and language certificates.
        """
        skills_data = validated_data.pop("skills_data", [])
        experiences_data = validated_data.pop("experiences_data", [])
        certificates_data = validated_data.pop("certificates_data", [])
        language_certificates_data = validated_data.pop("language_certificates_data", [])

        # Get the candidate from validated_data
        candidate = validated_data.get("candidate")

        # Check if this is the first resume BEFORE creating
        if candidate:
            is_first_resume = not Resume.objects.filter(candidate=candidate).exists()
            if is_first_resume:
                validated_data["is_main"] = True

        # Now create the resume (this calls save() with is_main already set)
        resume = super().create(validated_data)

        self._create_resume_skills(resume, skills_data)
        self._create_resume_experiences(resume, experiences_data)

        # Use the certificate service for creation
        if certificates_data:
            validated_certificates, _ = CertificateService.validate_certificates_data(certificates_data)
            CertificateService.create_resume_certificates(resume, validated_certificates)

        # Create language certificates
        if language_certificates_data:
            self._create_language_certificates(resume, language_certificates_data)

        return resume

    def update(self, instance, validated_data):
        """
        Update resume and efficiently manage skills, experiences, certificates,
        and language certificates.
        """
        skills_data = validated_data.pop("skills_data", None)
        experiences_data = validated_data.pop("experiences_data", None)
        certificates_data = validated_data.pop("certificates_data", None)
        language_certificates_data = validated_data.pop("language_certificates_data", None)

        # Handle certificates field if provided (for backward compatibility)
        certificates = validated_data.pop("certificates", None)
        if certificates is not None and certificates_data is None:
            certificates_data = certificates

        resume = super().update(instance, validated_data)

        if skills_data is not None:
            resume.resume_skills.all().delete()
            self._create_resume_skills(resume, skills_data)

        if experiences_data is not None:
            resume.experiences.all().delete()
            self._create_resume_experiences(resume, experiences_data)

        # Use the optimized certificate service for updates
        if certificates_data is not None:
            CertificateService.update_resume_certificates(resume, certificates_data)

        # Update language certificates
        if language_certificates_data is not None:
            self._update_language_certificates(resume, language_certificates_data)

        return resume

    def _create_resume_skills(self, resume, skills_data):
        """
        Helper method to create resume skills in bulk.
        Same pattern as VacancySerializer._create_vacancy_skills.
        """
        if not skills_data:
            return

        resume_skills = []
        for skill_data in skills_data:
            resume_skill = ResumeSkill(
                resume=resume,
                skill=skill_data["skill"],
                minimum_years=skill_data["minimum_years"],
                proficiency_level=skill_data["proficiency_level"],
            )
            resume_skills.append(resume_skill)

        # Bulk create for better performance
        ResumeSkill.objects.bulk_create(resume_skills)

    def _create_resume_experiences(self, resume, experiences_data):
        """Helper method to create resume experiences in bulk."""
        if not experiences_data:
            return

        experiences = []
        for exp_data in experiences_data:
            experience = ResumeExperience(
                resume=resume,
                company=exp_data["company"],
                role=exp_data["role"],
                country=exp_data.get("country", ""),
                city=exp_data.get("city", ""),
                start_date=exp_data.get("start_date"),
                end_date=exp_data.get("end_date"),
                description=exp_data.get("description", ""),
            )
            experiences.append(experience)

        ResumeExperience.objects.bulk_create(experiences)

    def _create_language_certificates(self, resume, language_certificates_data):
        """
        Create language certificates for a resume.
        Files are saved individually since bulk_create doesn't handle FileField uploads.
        """
        if not language_certificates_data:
            return

        for lc_data in language_certificates_data:
            ResumeLanguageCertificate.objects.create(
                resume=resume,
                language=lc_data["language"],
                level=lc_data["level"],
                file=lc_data.get("file"),
            )

    def _update_language_certificates(self, resume, language_certificates_data):
        """
        Update language certificates for a resume.

        Strategy:
        - Items with an 'id' field: update existing records
        - Items without 'id': create new records
        - Existing records NOT in the submitted list: delete with file cleanup
        """
        existing_ids = set(
            resume.language_certificates.values_list("id", flat=True)
        )
        submitted_ids = set()

        for lc_data in language_certificates_data:
            lc_id = lc_data.get("id")
            if lc_id and lc_id in existing_ids:
                # Update existing
                submitted_ids.add(lc_id)
                existing = resume.language_certificates.get(id=lc_id)
                existing.language = lc_data["language"]
                existing.level = lc_data["level"]
                if lc_data.get("file"):
                    # Clean old file before replacing
                    if existing.file and default_storage.exists(existing.file.name):
                        try:
                            default_storage.delete(existing.file.name)
                        except Exception:
                            logger.warning(f"Failed to delete old file for language certificate ID {existing.id}")
                    existing.file = lc_data["file"]
                existing.save()
            else:
                # Upsert by language to respect unique (resume, language)
                language = lc_data["language"]
                level = lc_data["level"]
                new_file = lc_data.get("file")
                existing = resume.language_certificates.filter(language=language).first()
                if existing:
                    submitted_ids.add(existing.id)
                    existing.level = level
                    if new_file:
                        # Clean old file before replacing
                        if existing.file and default_storage.exists(existing.file.name):
                            try:
                                default_storage.delete(existing.file.name)
                            except Exception:
                                logger.warning(f"Failed to delete old file for language certificate ID {existing.id}")
                        existing.file = new_file
                    existing.save()
                else:
                    created = ResumeLanguageCertificate.objects.create(
                        resume=resume,
                        language=language,
                        level=level,
                        file=new_file,
                    )
                    submitted_ids.add(created.id)
        
        # Delete removed entries with file cleanup
        ids_to_delete = existing_ids - submitted_ids
        if ids_to_delete:
            certs_to_delete = resume.language_certificates.filter(id__in=ids_to_delete)
            for cert in certs_to_delete:
                logger.warning(f"Deleting language certificate ID {cert.id}")
                cert.delete()  # triggers file cleanup in model's delete()

    def to_representation(self, instance):
        """
        Customize the representation of the resume data.
        Format current_salary to remove trailing .00 for whole numbers.
        """
        data = super().to_representation(instance)
        
        # Format current_salary to remove .00 for whole numbers
        if data.get('current_salary') is not None:
            try:
                # Convert Decimal to string and remove .00 if it's a whole number
                salary = data['current_salary']
                if isinstance(salary, str) and salary.endswith('.00'):
                    data['current_salary'] = salary[:-3]
            except (ValueError, AttributeError):
                logger.warning(f"Failed to format current_salary for resume ID {instance.id}")
        
        return data


class WorkStatusSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
