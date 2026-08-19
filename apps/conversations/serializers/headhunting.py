from rest_framework import serializers
from django.utils.translation import gettext as _
from apps.resumes.models import Resume
from apps.resumes.models.choices import WorkStatus
from apps.resumes.services.experience import (
    calculate_total_experience_months,
    format_experience
)
from django.utils import translation
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from utils.html_sanitizer import validate_safe_html

from apps.hr_templates.constants import ALL_VARIABLES, get_unknown_variables
from utils.language import get_request_language


class EduPartnerSummarySerializer(serializers.Serializer):
    """Shape of the `university` field on HeadhuntingCandidateSerializer."""

    id = serializers.UUIDField()
    name = serializers.CharField()


class HeadhuntingCandidateSerializer(serializers.ModelSerializer):
    """
    Serializer for headhunting candidates list.

    Returns candidate information with resume details for recruiters
    to find and headhunt potential candidates.
    """

    resume_id = serializers.UUIDField(source='id', read_only=True)
    candidate_id = serializers.UUIDField(source='candidate.id', read_only=True)
    candidate_email = serializers.EmailField(source='candidate.email', read_only=True)
    full_name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    photo = serializers.SerializerMethodField()
    position = serializers.CharField(read_only=True)
    work_status = serializers.CharField(read_only=True)
    work_status_display = serializers.SerializerMethodField()
    current_salary = serializers.SerializerMethodField()
    salary_currency = serializers.SerializerMethodField()
    total_experience = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    similarity_score = serializers.SerializerMethodField()
    university = serializers.SerializerMethodField()

    class Meta:
        model = Resume
        fields = [
            'resume_id',
            'candidate_id',
            'candidate_email',
            'full_name',
            'phone',
            'photo',
            'position',
            'work_status',
            'work_status_display',
            'current_salary',
            'salary_currency',
            'total_experience',
            'date_of_birth',
            'similarity_score',
            'university',
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_similarity_score(self, obj):
        """
        Return the vacancy-match similarity score if the view attached one
        (only present when the request was filtered by vacancy_id).
        """
        score = getattr(obj, 'similarity_score', None)
        return round(score, 3) if score is not None else None

    def get_full_name(self, obj):
        """
        Get candidate's full name from prefetched profile.
        """
        profile = getattr(obj.candidate, 'candidateprofile', None)
        if profile:
            return profile.full_name
        return obj.candidate.email

    def get_phone(self, obj):
        """
        Get candidate's phone from prefetched profile.
        """
        profile = getattr(obj.candidate, 'candidateprofile', None)
        if profile:
            return profile.phone
        return None

    def get_photo(self, obj):
        """
        Get candidate's photo URL from prefetched profile.
        """
        profile = getattr(obj.candidate, 'candidateprofile', None)
        if profile and profile.photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return None

    def get_work_status_display(self, obj):
        """
        Get human-readable work status.
        """
        language = translation.get_language()
        localized_statuses = {item['key']: item['label'] for item in WorkStatus.get_localized_statuses(language)}
        return localized_statuses.get(obj.work_status, obj.get_work_status_display())

    def get_current_salary(self, obj):
        """
        Get candidate's current salary, treating null as 0.
        Respects salary_hide — returns "-" if candidate chose to hide salary.
        """
        if obj.salary_hide:
            return "-"
        expected_salary = obj.current_salary if obj.current_salary is not None else 0
        expected_salary = "-" if not expected_salary else f"{expected_salary:,.0f}".replace(",", " ")
        return expected_salary

    def get_salary_currency(self, obj):
        """
        Get salary currency, hidden if salary_hide is True.
        """
        if obj.salary_hide:
            return None
        return obj.salary_currency

    def get_total_experience(self, obj):
        experiences = getattr(obj, 'prefetched_experiences', None)
        if experiences is None:
            # Fallback: prefetch wasn't applied (shouldn't happen in normal flow)
            experiences = list(obj.experiences.only('id', 'resume_id', 'start_date', 'end_date'))

        intervals = [
            (exp.start_date, exp.end_date)
            for exp in experiences
            if exp.start_date
        ]
        total_months = calculate_total_experience_months(intervals)
        return format_experience(total_months)

    def get_date_of_birth(self, obj):
        """
        Get candidate's date of birth in ISO 8601 format (YYYY-MM-DD).
        """
        if obj.candidate.date_of_birth:
            return obj.candidate.date_of_birth.isoformat()
        return None

    @extend_schema_field(EduPartnerSummarySerializer)
    def get_university(self, obj) -> dict | None:
        """
        Candidate's educational partner (university).
        Relies on `candidate__edupartner` being select_related by the view's
        queryset - no extra query is issued here.
        """
        edupartner = getattr(obj.candidate, "edupartner", None)
        if edupartner is None:
            return None

        language = get_request_language()
        if language == "ru":
            name = edupartner.name_ru or edupartner.name_en
        elif language == "uz":
            name = edupartner.name_uz or edupartner.name_en
        else:
            name = edupartner.name_en

        return {
            "id": edupartner.id,
            "name": name,
        }


class HeadhuntingInvitationSerializer(serializers.Serializer):
    """
    Serializer for sending headhunting invitations to candidates.

    Allows recruiters to send invitation letters to selected candidates.
    """

    candidate_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=50,
        help_text=_("List of candidate IDs to send invitation to (max 50)"),
    )
    letter = serializers.CharField(
        min_length=10,
        max_length=5000,
        help_text=_("The invitation letter content with optional template variables (10-5000 characters)"),
    )
    vacancy_id = serializers.UUIDField(
        required=True,
        help_text=_("The vacancy to invite candidates for"),
    )

    def validate_candidate_ids(self, value):
        """
        Validate that all candidate IDs exist and deduplicate.
        """
        from apps.authentication.models import Candidate

        value = list(dict.fromkeys(value))

        existing_ids = set(
            Candidate.objects.filter(id__in=value).values_list('id', flat=True)
        )
        missing_ids = set(value) - existing_ids

        if missing_ids:
            raise serializers.ValidationError(
                f"Candidates not found: {list(missing_ids)}"
            )

        return value

    def validate_letter(self, value):
        unknown = get_unknown_variables(value)
        if unknown:
            raise serializers.ValidationError(
                _("Unknown template variable(s): %(variables)s. Allowed variables: %(allowed)s.")
                % {
                    "variables": ", ".join(sorted(unknown)),
                    "allowed": ", ".join(sorted(ALL_VARIABLES)),
                }
            )
        return validate_safe_html(value)

    def validate_vacancy_id(self, value):
        """
        Validate that vacancy exists, is active, and belongs to recruiter's company.
        Reuses the cached recruiter from the permission layer to avoid extra queries.
        Stores the resolved vacancy in serializer context for the view to reuse.
        """
        from apps.vacancies.models import Vacancy
        from apps.subscriptions.permissions import get_cached_recruiter

        request = self.context.get('request')
        if not request or not request.user:
            return value

        try:
            vacancy = Vacancy.objects.get(id=value)
            if not vacancy.is_active:
                raise serializers.ValidationError(
                    "Cannot use inactive vacancy for invitations"
                )
            # Reuse recruiter from the permission layer cache
            recruiter = get_cached_recruiter(request) if request else None
            if recruiter is not None:
                company_id = recruiter.company_id
            else:
                # Fallback: lightweight query for company_id only
                from apps.authentication.models import Recruiter
                try:
                    recruiter = Recruiter.objects.only('company_id').get(id=request.user.id)
                    company_id = recruiter.company_id
                except Recruiter.DoesNotExist:
                    raise serializers.ValidationError(
                        _("Authenticated user is not a recruiter")
                    )
            if vacancy.company_id != company_id:
                raise serializers.ValidationError(
                    _("This vacancy does not belong to your company")
                )
            self.context['validated_vacancy'] = vacancy
        except Vacancy.DoesNotExist:
            raise serializers.ValidationError(_("Vacancy not found"))

        return value


