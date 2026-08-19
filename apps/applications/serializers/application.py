import os
import logging

from rest_framework import serializers
from django.utils import timezone
from django.utils.translation import gettext as _
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError

from ..models import JobApplication, ApplicationStatus, ApplicationDocument
from apps.vacancies.models import Vacancy
from apps.vacancies.services.skill_matcher import SkillMatcherService
from apps.vacancies.serializers.skill_match import SkillMatchSerializer
from apps.resumes.models import Resume
from apps.authentication.models import Candidate
from .document import ApplicationDocumentSerializer
from .candidate_company import CandidateCompanySummarySerializer
from drf_spectacular.utils import extend_schema_field, OpenApiTypes
from utils.language import get_request_language
from utils import validate_uploaded_file

from utils.html_sanitizer import validate_safe_html
from apps.hr_templates.constants import ALL_VARIABLES, get_unknown_variables

logger = logging.getLogger(__name__)


class JobApplicationCreateSerializer(serializers.ModelSerializer):
    """
    Optimized serializer that reuses already-fetched objects from context.
    """

    # Accept vacancy by ID, but we'll validate it exists and is active
    vacancy_id = serializers.UUIDField(write_only=True)

    # Optional resume selection - if not provided, we'll try to use their latest resume
    resume_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    # Accept raw file uploads for application documents
    documents_data = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
        help_text="List of document files to attach to the application.",
    )

    class Meta:
        model = JobApplication
        fields = [
            "vacancy_id",
            "resume_id",
            "cover_letter",
            "portfolio_url",
            "earliest_start_date",
            "documents_data",
        ]
        extra_kwargs = {
            'cover_letter': {'required': False, 'allow_blank': True},
            'portfolio_url': {'required': False, 'allow_blank': True},
            'earliest_start_date': {'required': False},
        }

    def validate_vacancy_id(self, value):
        vacancy = self.context.get("vacancy")

        if vacancy and str(vacancy.id) == str(value):
            return value

        try:
            vacancy = Vacancy.objects.select_related("company", "created_by").get(
                id=value
            )
        except Vacancy.DoesNotExist:
            raise serializers.ValidationError(_("Vacancy not found"))

        if not vacancy.is_active:
            raise serializers.ValidationError(
                _("This vacancy is no longer accepting applications")
            )

        if getattr(vacancy, "is_demo", False):
            raise serializers.ValidationError(
                _("This vacancy is not accepting applications")
            )

        return value

    def validate_resume_id(self, value):
        return value

    def validate_portfolio_url(self, value):
        if value and value.lower().startswith("javascript:"):
            raise serializers.ValidationError(_("Invalid URL scheme"))
        return value

    def validate_earliest_start_date(self, value):
        if value and value < timezone.now().date():
            raise serializers.ValidationError(_("Start date cannot be in the past"))
        return value

    def validate_documents_data(self, value):
        for file_obj in value:
            validate_uploaded_file(file_obj)
        return value

    def validate(self, attrs):
        candidate = self.context.get("candidate")

        if not candidate:
            user = self.context["request"].user
            try:
                candidate = Candidate.objects.get(email=user.email)
            except Candidate.DoesNotExist:
                raise serializers.ValidationError(
                    {"detail": _("Candidate profile not found")}
                )

        vacancy = self.context.get("vacancy")

        if not vacancy:
            vacancy_id = attrs.get("vacancy_id")
            if vacancy_id:
                try:
                    vacancy = Vacancy.objects.select_related(
                        "company", "created_by"
                    ).get(id=vacancy_id)
                except Vacancy.DoesNotExist:
                    raise serializers.ValidationError(
                        {"vacancy_id": _("Vacancy not found")}
                    )

        resume = None
        resume_id = attrs.get("resume_id")

        if resume_id:
            try:
                resume = Resume.objects.only("id", "candidate_id", "title").get(
                    id=resume_id,
                    candidate_id=candidate.id,
                )
            except Resume.DoesNotExist:
                raise serializers.ValidationError(
                    {"resume_id": "Resume not found or you don't have permission to use it"}
                )
        else:
            try:
                resume = (
                    Resume.objects.filter(candidate_id=candidate.id)
                    .only("id", "candidate_id", "title")
                    .order_by("-created_at")
                    .first()
                )
            except Exception:
                logger.error(f"Error fetching latest resume for candidate {candidate.id}", exc_info=True)

        attrs['_candidate'] = candidate
        attrs['_vacancy'] = vacancy
        attrs['_resume'] = resume

        return attrs

    def create(self, validated_data):
        candidate = validated_data.pop("_candidate")
        vacancy = validated_data.pop("_vacancy")
        resume = validated_data.pop("_resume", None)

        validated_data.pop("vacancy_id", None)
        validated_data.pop("resume_id", None)
        documents_data = validated_data.pop("documents_data", [])

        validated_data["candidate"] = candidate
        validated_data["vacancy"] = vacancy

        if resume:
            validated_data["resume_used"] = resume

        from apps.applications.models import ApplicationStatusModel, StatusCategory
        from apps.vacancies.models import Vacancy as _Vacancy
        company = vacancy.company
        initial_status_key = ApplicationStatus.APPLIED

        applied_status = (
            ApplicationStatusModel.objects.filter(
                company=company,
                category__key=StatusCategory.APPLIED,
                is_active=True,
            )
            .select_related("category")
            .order_by("-is_default", "position")
            .first()
        )
        if applied_status:
            initial_status_key = applied_status.key

        self._applied_status_model = applied_status

        validated_data["status"] = initial_status_key

        company_vacancy_ids = _Vacancy.objects.filter(
            company_id=company.id
        ).values("id")
        last_position = JobApplication.objects.filter(
            vacancy_id__in=company_vacancy_ids,
            status=initial_status_key,
        ).order_by("-kanban_position").values_list("kanban_position", flat=True).first()
        validated_data["kanban_position"] = (
            last_position + 1 if last_position is not None else 0
        )

        application = JobApplication(**validated_data)
        application._cached_is_hired = False
        application.save(skip_full_clean=True)

        created_documents = []
        if documents_data:
            documents = []
            for file_obj in documents_data:
                doc = ApplicationDocument(
                    application=application,
                    file=file_obj,
                )
                if hasattr(file_obj, "size"):
                    doc.file_size = file_obj.size
                if hasattr(file_obj, "name"):
                    doc.title = os.path.basename(file_obj.name)
                documents.append(doc)
            created_documents = ApplicationDocument.objects.bulk_create(documents)

        self.resume = resume
        self.created_documents = created_documents

        return application


class JobApplicationListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing applications.
    """

    company_id = serializers.UUIDField(source="vacancy.company.id", read_only=True)
    company_name = serializers.CharField(source="vacancy.company.name", read_only=True)

    title = serializers.CharField(source="vacancy.title", read_only=True)
    vacancy_id = serializers.UUIDField(source="vacancy.id", read_only=True)
    about_us = serializers.CharField(source="vacancy.about_us", read_only=True)
    requirements = serializers.CharField(source="vacancy.requirements", read_only=True)
    responsibilities = serializers.CharField(source="vacancy.responsibilities", read_only=True)
    additional_info = serializers.CharField(source="vacancy.additional_info", read_only=True)
    expire = serializers.IntegerField(source="vacancy.expire", read_only=True)
    experience = serializers.IntegerField(source="vacancy.experience", read_only=True)
    salary_min = serializers.DecimalField(source="vacancy.salary_min", max_digits=15, decimal_places=2, read_only=True)
    salary_max = serializers.DecimalField(source="vacancy.salary_max", max_digits=15, decimal_places=2, read_only=True)
    salary_currency = serializers.CharField(source="vacancy.salary_currency", read_only=True)
    status_display = serializers.SerializerMethodField()
    recruiter_email = serializers.EmailField(source="vacancy.created_by.email", read_only=True)
    days_since_application = serializers.ReadOnlyField()
    can_withdraw = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "company_id",
            "company_name",
            "title",
            "vacancy_id",
            "about_us",
            "requirements",
            "responsibilities",
            "additional_info",
            "expire",
            "experience",
            "salary_min",
            "salary_max",
            "salary_currency",
            "status",
            "status_display",
            "recruiter_email",
            "applied_at",
            "updated_at",
            "days_since_application",
            "can_withdraw",
        ]

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_can_withdraw(self, obj) -> bool:
        status_terminal_map = self.context.get("status_terminal_map")
        if status_terminal_map is not None and obj.status in status_terminal_map:
            return not status_terminal_map[obj.status]

        return obj.can_be_withdrawn()

    @extend_schema_field(OpenApiTypes.STR)
    def get_status_display(self, obj) -> str:
        if not hasattr(self, '_cached_translations'):
            self._cached_translations = ApplicationStatus.get_translations()
            self._cached_language = get_request_language()
        try:
            status_obj = ApplicationStatus(obj.status)
            return self._cached_translations.get(status_obj, {}).get(
                self._cached_language,
                obj.get_status_display(self._cached_language),
            )
        except ValueError:
            return obj.get_status_display(self._cached_language)


class JobApplicationDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for detailed application views.
    """

    # Vacancy information
    vacancy_title = serializers.CharField(source="vacancy.title", read_only=True)
    vacancy_description = serializers.CharField(
        source="vacancy.description", read_only=True
    )
    company_name = serializers.CharField(source="vacancy.company.name", read_only=True)
    employment_type = serializers.SerializerMethodField()

    # Candidate information (visible to recruiters)
    candidate_email = serializers.CharField(source="candidate.email", read_only=True)
    candidate_name = serializers.SerializerMethodField()
    candidate_img_url = serializers.SerializerMethodField()

    # Resume information
    resume_title = serializers.CharField(source="resume_used.title", read_only=True)
    resume_id = serializers.SerializerMethodField()
    expected_salary = serializers.SerializerMethodField()
    salary_currency = serializers.SerializerMethodField()

    # Status and metadata
    status_display = serializers.SerializerMethodField()
    status_category = serializers.SerializerMethodField()
    days_since_application = serializers.ReadOnlyField()
    is_recent = serializers.ReadOnlyField()
    can_withdraw = serializers.SerializerMethodField()

    # Related documents
    documents = ApplicationDocumentSerializer(many=True, read_only=True)

    # Recruiter information
    responsible_recruiter = serializers.SerializerMethodField()
    assignee = serializers.SerializerMethodField()

    # AI evaluation summary
    ai_evaluation = serializers.SerializerMethodField()

    # Skill matching
    skill_match = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "applied_at",
            "updated_at",
            # Vacancy details
            "vacancy_title",
            "vacancy_description",
            "company_name",
            "employment_type",
            "assignee",
            # Candidate details
            "candidate_email",
            "candidate_name",
            "candidate_img_url",
            # Application content
            "cover_letter",
            "portfolio_url",
            "earliest_start_date",
            # Resume information
            "resume_title",
            "resume_id",
            "expected_salary",
            "salary_currency",
            # Status and tracking
            "status",
            "status_display",
            "status_category",
            "days_since_application",
            "is_recent",
            "can_withdraw",
            # Recruiter notes
            "recruiter_notes",
            "responsible_recruiter",
            # Related data
            "documents",
            # AI evaluation
            "ai_evaluation",
            # Skill matching
            "skill_match",
        ]

    def get_responsible_recruiter(self, obj):
        recruiter_name_map = self.context.get("recruiter_name_map")
        if recruiter_name_map is not None:
            return recruiter_name_map.get(obj.vacancy.created_by_id)

        annotated = getattr(obj, "_recruiter_full_name", None)
        if annotated is not None:
            return annotated
        created_by = getattr(obj.vacancy, "created_by", None)
        if created_by is None:
            return None
        prefetched = getattr(created_by, "prefetched_profiles", None)
        if prefetched is not None:
            return prefetched[0].full_name if prefetched else None
        return None

    def get_candidate_name(self, obj) -> str:
        profile = getattr(obj.candidate, "candidateprofile", None)
        if profile:
            return profile.full_name
        return obj.candidate.email

    def get_candidate_img_url(self, obj) -> str:
        profile = getattr(obj.candidate, "candidateprofile", None)
        if profile and profile.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return None

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_can_withdraw(self, obj) -> bool:
        status_terminal_map = self.context.get("status_terminal_map")
        if status_terminal_map is not None and obj.status in status_terminal_map:
            return not status_terminal_map[obj.status]

        return obj.can_be_withdrawn()

    @extend_schema_field(OpenApiTypes.UUID)
    def get_resume_id(self, obj):
        return obj.resume_used_id

    @extend_schema_field(OpenApiTypes.STR)
    def get_employment_type(self, obj) -> str:
        language = get_request_language()
        employment_type_value = obj.vacancy.employment_type
        translations = {
            "FULL_TIME": {"en": "Full Time", "ru": "Полная занятость", "uz": "To'liq bandlik"},
            "PART_TIME": {"en": "Part Time", "ru": "Частичная занятость", "uz": "Yarim stavka"},
            "CONTRACT": {"en": "Contract", "ru": "Контракт", "uz": "Shartnoma"},
            "INTERNSHIP": {"en": "Internship", "ru": "Стажировка", "uz": "Amaliyot"},
        }
        return translations.get(employment_type_value, {}).get(language, employment_type_value)

    @extend_schema_field(OpenApiTypes.STR)
    def get_expected_salary(self, obj):
        if obj.resume_used and not obj.resume_used.salary_hide:
            expected_salary = obj.resume_used.current_salary
            expected_salary = "-" if not expected_salary else f"{expected_salary:,.0f}".replace(",", " ")
            return expected_salary
        return "-"

    @extend_schema_field(OpenApiTypes.STR)
    def get_salary_currency(self, obj):
        if obj.resume_used and not obj.resume_used.salary_hide:
            return obj.resume_used.salary_currency
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_status_display(self, obj) -> str:
        status_labels = self.context.get("status_labels")
        if status_labels is not None and obj.status in status_labels:
            return status_labels[obj.status]

        if not hasattr(self, '_cached_translations'):
            self._cached_translations = ApplicationStatus.get_translations()
            self._cached_language = get_request_language()
        try:
            status_obj = ApplicationStatus(obj.status)
            return self._cached_translations.get(status_obj, {}).get(
                self._cached_language,
                obj.get_status_display(self._cached_language),
            )
        except ValueError:
            return obj.get_status_display(self._cached_language)

    @extend_schema_field(OpenApiTypes.STR)
    def get_status_category(self, obj) -> str | None:
        from apps.applications.models import ApplicationStatusModel

        status_category_map = self.context.get("status_category_map")
        if status_category_map is not None and obj.status in status_category_map:
            return status_category_map[obj.status]

        status_model = (
            ApplicationStatusModel.objects.filter(
                company=obj.vacancy.company,
                key=obj.status,
                is_active=True,
            )
            .select_related("category")
            .only("key", "company_id", "category__key")
            .first()
        )
        if status_model is not None:
            return status_model.category.key

        return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return representation

        user = request.user

        if user.is_candidate:
            sensitive_fields = ["recruiter_notes", "responsible_recruiter"]
            for field in sensitive_fields:
                representation.pop(field, None)

        elif user.is_recruiter:
            logger.debug(f"Recruiter {user.email} is viewing application {instance.id}")
            if "ai_evaluation" in representation and isinstance(representation["ai_evaluation"], dict):
                representation["ai_evaluation"].pop("rejection_summary", None)

        return representation

    def get_assignee(self, obj):
        return self.get_responsible_recruiter(obj)

    def get_ai_evaluation(self, obj) -> dict:
        """Return AI evaluation status, score, and rejection summary if available."""
        result = {"status": "pending", "overall_score": None}
        try:
            ev = obj.ai_evaluation
            result["status"] = ev.status
            result["overall_score"] = ev.overall_score
        except ObjectDoesNotExist:
            return result
        try:
            roadmap = obj.vacancy_skill_roadmap
        except ObjectDoesNotExist:
            roadmap = None
        if roadmap is not None and roadmap.rejection_summary:
            result["rejection_summary"] = roadmap.rejection_summary
        return result

    @extend_schema_field(SkillMatchSerializer)
    def get_skill_match(self, obj) -> dict | None:
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return None

        user = request.user

        if user.is_candidate:
            if hasattr(user, 'email') and obj.candidate.email != user.email:
                return None

        main_resume = None
        candidate = obj.candidate

        if obj.resume_used is not None:
            main_resume = obj.resume_used
        else:
            prefetched_main_resumes = getattr(candidate, "prefetched_main_resumes", None)
            if prefetched_main_resumes is not None:
                main_resume = prefetched_main_resumes[0] if prefetched_main_resumes else None
            else:
                main_resume = candidate.resumes.filter(
                    is_main=True
                ).prefetch_related(
                    'resume_skills__skill'
                ).first()

        if main_resume is None:
            return None

        if not hasattr(self, "_vacancy_skills_cache"):
            self._vacancy_skills_cache = {}

        vacancy_id = obj.vacancy_id
        vacancy_skills = self._vacancy_skills_cache.get(vacancy_id)
        if vacancy_skills is None:
            vacancy_skills = SkillMatcherService.get_vacancy_skills(obj.vacancy)
            self._vacancy_skills_cache[vacancy_id] = vacancy_skills

        if not vacancy_skills:
            return None

        resume_skills = SkillMatcherService.get_resume_skills(main_resume)
        return SkillMatcherService.calculate_match(vacancy_skills, resume_skills).to_dict()


class CompanyCandidatesApplicationSerializer(JobApplicationDetailSerializer):
    """Company-candidates serializer with flat status fields including color."""

    status_color = serializers.SerializerMethodField()
    discussion_count = serializers.IntegerField(read_only=True, default=0)
    company_applications = serializers.SerializerMethodField()

    class Meta(JobApplicationDetailSerializer.Meta):
        fields = JobApplicationDetailSerializer.Meta.fields + [
            "status_color",
            "discussion_count",
            "company_applications",
        ]

    @extend_schema_field(CandidateCompanySummarySerializer)
    def get_company_applications(self, obj) -> dict | None:
        """
        Summary of all applications this candidate submitted to the company:
        total count + the best AI-match application (score, status, recruiter).
        Populated from a bulk map computed once per page by the view.
        """
        summary_map = self.context.get("company_applications_map")
        if summary_map is None:
            return None
        return summary_map.get(obj.candidate_id)

    def get_status_color(self, obj) -> str | None:
        from apps.applications.models import ApplicationStatusModel

        status_color_map = self.context.get("status_color_map")
        if status_color_map is not None and obj.status in status_color_map:
            return status_color_map[obj.status]

        status_model = (
            ApplicationStatusModel.objects.filter(
                company=obj.vacancy.company,
                key=obj.status,
                is_active=True,
            )
            .only("key", "company_id", "color")
            .first()
        )
        if status_model is not None:
            return status_model.color

        return None


class JobApplicationUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating application status and recruiter notes.
    """

    status = serializers.ChoiceField(choices=ApplicationStatus.choices, required=False)

    kanban_position = serializers.IntegerField(
        min_value=0,
        required=False,
        help_text="Position in Kanban column (0-indexed). Position 0 means top of column."
    )

    title = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Optional title for the recruiter notes.",
    )

    class Meta:
        model = JobApplication
        fields = [
            "status",
            "recruiter_notes",
            "earliest_start_date",
            "kanban_position",
            "title",
        ]

    def validate_recruiter_notes(self, value):
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

    def validate_status(self, value):
        if not value:
            return value

        current_status = self.instance.status if self.instance else None

        if current_status and current_status == value:
            return value

        # ponytail: delegate transition validation to the model's method
        # instead of maintaining a third copy of the rules.
        try:
            self.instance.validate_status_transition(value, user_type="recruiter")
        except DjangoValidationError as e:
            raise serializers.ValidationError(str(e))

        return value

    def validate_kanban_position(self, value):
        if value is None:
            return value

        instance = self.instance
        if instance is None:
            return value

        if instance.kanban_position == value:
            return value

        target_status = self.initial_data.get("status") or getattr(instance, "status", None)
        if target_status is None:
            return value

        company = getattr(instance.vacancy, "company", None) if hasattr(instance, "vacancy") else None
        if company is None:
            return value

        current_status = getattr(instance, "status", None)
        is_same_column = (target_status == current_status)

        from apps.applications.models import JobApplication

        queryset = JobApplication.objects.filter(
            vacancy__company=company,
            status=target_status,
        )

        if not is_same_column:
            queryset = queryset.exclude(id=instance.id)

        total_count = queryset.count()

        if total_count == 0:
            if value != 0:
                raise serializers.ValidationError(
                    "kanban_position must be 0 for an empty column."
                )
        else:
            max_allowed = total_count - 1 if is_same_column else total_count

            if value > max_allowed:
                raise serializers.ValidationError(
                    f"kanban_position must be between 0 and {max_allowed} for this column."
                )

        return value

    def validate(self, attrs):
        new_status = attrs.get('status')
        recruiter_notes = attrs.get('recruiter_notes', '').strip()

        if new_status == ApplicationStatus.REJECTED and not recruiter_notes:
            raise serializers.ValidationError({
                'recruiter_notes': _('Please provide a reason when rejecting an application.')
            })

        return attrs
