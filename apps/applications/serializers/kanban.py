"""
Serializers for Kanban board functionality.

These serializers handle the grouped response format for Kanban views.
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, OpenApiTypes

from apps.applications.models import JobApplication, ApplicationStatus
from apps.vacancies.serializers.skill_match import SkillMatchSerializer
from apps.vacancies.services.skill_matcher import SkillMatcherService
from utils.language import get_request_language


class KanbanApplicationSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer optimized for Kanban board display.
    
    Contains essential information for the Kanban card without
    heavy nested objects that would slow down the grouped response.
    
    IMPORTANT: This serializer expects the queryset to have:
    - select_related: candidate, candidate__candidateprofile, vacancy, 
      vacancy__company, vacancy__created_by, vacancy__created_by__recruiterprofile,
      resume_used
    - prefetch_related: vacancy__vacancyskill_set__skill,
      candidate__resumes (filtered to is_main=True), 
      candidate__resumes__resume_skills__skill (for skill_match)
    """

    # Candidate information
    candidate_name = serializers.SerializerMethodField()
    candidate_email = serializers.CharField(source="candidate.email", read_only=True)
    candidate_img_url = serializers.SerializerMethodField()
    candidate_address = serializers.SerializerMethodField()

    # Vacancy information
    vacancy_id = serializers.UUIDField(source="vacancy.id", read_only=True)
    vacancy_title = serializers.CharField(source="vacancy.title", read_only=True)
    company_name = serializers.CharField(source="vacancy.company.name", read_only=True)

    # Resume information
    resume_title = serializers.SerializerMethodField()
    resume_id = serializers.SerializerMethodField()

    # Salary from resume (displayed as expected_salary in response)
    expected_salary = serializers.SerializerMethodField()
    salary_currency = serializers.SerializerMethodField()

    # Status and position
    status_display = serializers.SerializerMethodField()

    # Assignee (recruiter who created the vacancy) - uses prefetched data
    assignee = serializers.SerializerMethodField()

    # Skill matching for recruiter view
    skill_match = serializers.SerializerMethodField()

    # AI evaluation summary
    ai_evaluation = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = [
            "id",
            "status",
            "status_display",
            "kanban_position",
            "applied_at",
            "updated_at",
            # Candidate info
            "candidate_name",
            "candidate_email",
            "candidate_img_url",
            "candidate_address",
            # Vacancy info
            "vacancy_id",
            "vacancy_title",
            "company_name",
            # Resume info
            "resume_title",
            "resume_id",
            # Salary info
            "expected_salary",
            "salary_currency",
            # Assignee
            "assignee",
            # Skill matching
            "skill_match",
            # AI evaluation
            "ai_evaluation",
        ]

    def get_candidate_name(self, obj) -> str:
        candidateprofile = getattr(obj.candidate, 'candidateprofile', None)
        if candidateprofile and candidateprofile.full_name:
            return candidateprofile.full_name
        return obj.candidate.email

    @extend_schema_field(OpenApiTypes.URI)
    def get_candidate_img_url(self, obj):
        candidateprofile = getattr(obj.candidate, 'candidateprofile', None)
        if candidateprofile and candidateprofile.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(candidateprofile.photo.url)
            return candidateprofile.photo.url
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_resume_title(self, obj):
        if obj.resume_used:
            return obj.resume_used.title
        return None

    @extend_schema_field(OpenApiTypes.UUID)
    def get_resume_id(self, obj):
        return obj.resume_used_id

    @extend_schema_field(OpenApiTypes.STR)
    def get_expected_salary(self, obj):
        if obj.resume_used and not obj.resume_used.salary_hide and obj.resume_used.current_salary is not None:
            expected_salary = obj.resume_used.current_salary
            expected_salary = "-" if not expected_salary else f"{expected_salary:,.0f}".replace(",", " ")
            return expected_salary
        return "-"

    @extend_schema_field(OpenApiTypes.STR)
    def get_salary_currency(self, obj):
        if obj.resume_used and not obj.resume_used.salary_hide:
            return obj.resume_used.salary_currency
        return "UZS"

    @extend_schema_field(OpenApiTypes.STR)
    def get_status_display(self, obj) -> str:
        status_labels = self.context.get("status_labels")
        if status_labels and obj.status in status_labels:
            return status_labels[obj.status]

        if not hasattr(self, '_cached_translations'):
            self._cached_translations = ApplicationStatus.get_translations()
            self._cached_language = get_request_language()
        try:
            status_obj = ApplicationStatus(obj.status)
            lang_translations = self._cached_translations.get(status_obj, {})
            if self._cached_language in lang_translations:
                return lang_translations[self._cached_language]
            return next(iter(lang_translations.values()), str(obj.status).replace("_", " ").title())
        except ValueError:
            return obj.get_status_display(self._cached_language)

    @extend_schema_field(OpenApiTypes.STR)
    def get_candidate_address(self, obj):
        candidateprofile = getattr(obj.candidate, 'candidateprofile', None)
        if candidateprofile and candidateprofile.address:
            return candidateprofile.address
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_assignee(self, obj):
        assignee_map = self.context.get("assignee_map")
        if assignee_map is not None:
            return assignee_map.get(obj.vacancy.created_by_id)

        created_by = getattr(obj.vacancy, 'created_by', None)
        if created_by:
            prefetched_profiles = getattr(created_by, 'prefetched_profiles', None)
            if prefetched_profiles:
                return prefetched_profiles[0].full_name
        return None

    @extend_schema_field(SkillMatchSerializer)
    def get_skill_match(self, obj) -> dict | None:
        candidate = obj.candidate
        main_resume = None

        prefetched_main_resumes = getattr(candidate, "prefetched_main_resumes", None)
        if prefetched_main_resumes is not None:
            main_resume = prefetched_main_resumes[0] if prefetched_main_resumes else None
        else:
            resumes = getattr(candidate, '_prefetched_objects_cache', {}).get('resumes', None)
            if resumes is not None:
                for resume in resumes:
                    if resume.is_main:
                        main_resume = resume
                        break
            elif obj.resume_used and obj.resume_used.is_main:
                main_resume = obj.resume_used
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

    def get_ai_evaluation(self, obj) -> dict:
        """Return AI evaluation status and score for the kanban card."""
        try:
            ev = obj.ai_evaluation
            return {"status": ev.status, "overall_score": ev.overall_score}
        except Exception:
            return {"status": "pending", "overall_score": None}


class KanbanColumnSerializer(serializers.Serializer):
    """
    Serializer for a single Kanban column.
    """

    key = serializers.CharField(help_text="The status key (e.g., 'APPLIED')")
    label = serializers.CharField(help_text="Localized display label")
    count = serializers.IntegerField(help_text="Total number of applications in this column")
    applications = KanbanApplicationSerializer(many=True, help_text="List of applications")
    has_more = serializers.BooleanField(help_text="Whether there are more applications to load")


class KanbanResponseSerializer(serializers.Serializer):
    """
    Serializer for the complete Kanban board response.
    
    Groups applications by status with pagination info for each column.
    """

    columns = serializers.ListField(
        child=KanbanColumnSerializer(),
        help_text="List of all status columns with their applications"
    )
    page_size = serializers.IntegerField(help_text="Number of applications per column")
    page = serializers.IntegerField(help_text="Current page number")
