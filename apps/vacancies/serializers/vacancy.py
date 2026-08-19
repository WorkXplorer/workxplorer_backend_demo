import logging
from rest_framework import serializers
from ...skills.models import Skill
from ..models import VacancyLanguage, VacancySkill, Vacancy, VacancyView
from apps.domain.models import Domain
from apps.applications.models.choices import ApplicationStatus
from apps.languages.models import Language
from apps.resumes.models.choices import LanguageProficiencyLevel
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema_field
from utils.language import get_request_language
from apps.vacancies.localization import get_localized_choices
from apps.vacancies.serializers.skill_match import SkillMatchSerializer
from apps.student_analytics.serializers import VacancySkillRoadmapSerializer
from apps.vacancies.services.skill_matcher import SkillMatcherService
from apps.skills.localization import localized_skill_name, user_preferred_language
from apps.subscriptions.models import CompanySubscription
from utils.html_sanitizer import validate_safe_html

logger = logging.getLogger(__name__)


class VacancyViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = VacancyView
        exclude = ["duration_seconds"]


class VacancySkillSerializer(serializers.ModelSerializer):
    skill_name = serializers.SerializerMethodField()
    skill_id = serializers.IntegerField(source="skill.id", read_only=True)
    skill_is_active = serializers.BooleanField(source="skill.is_active", read_only=True)

    class Meta:
        model = VacancySkill
        fields = [
            "skill_id",
            "skill_name",
            "is_required",
            "minimum_years",
            "proficiency_level",
            "skill_is_active",
        ]

    def get_skill_name(self, obj):
        request = self.context.get("request")
        return localized_skill_name(
            obj.skill,
            user_preferred_language(getattr(request, "user", None)),
        )


class VacancyLanguageSerializer(serializers.ModelSerializer):
    language_id = serializers.IntegerField(source="language.id", read_only=True)
    language_name = serializers.CharField(source="language.name", read_only=True)
    language_code = serializers.CharField(source="language.code", read_only=True)

    class Meta:
        model = VacancyLanguage
        fields = ["language_id", "language_name", "language_code", "level"]


class VacancySerializer(serializers.ModelSerializer):
    created_by = serializers.UUIDField(read_only=True)
    company_id = serializers.UUIDField(source="company.id", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    company_is_active = serializers.BooleanField(source="company.is_active", read_only=True)
    recruiter_email = serializers.CharField(source="created_by.email", read_only=True)
    domain_name = serializers.CharField(source="domain.name", read_only=True)

    vacancy_skills = VacancySkillSerializer(
        source="vacancyskill_set", many=True, read_only=True
    )

    skills_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text='List of skills with requirements. Format: [{"skill_id": <int>, "is_required": <bool>, "minimum_years": <int>, "proficiency_level": "BEGINNER|INTERMEDIATE|ADVANCED|EXPERT"}]',
    )

    vacancy_languages = VacancyLanguageSerializer(
        many=True, read_only=True
    )

    languages_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text='List of required languages with CEFR proficiency levels. Format: [{"language_id": <int>, "level": "A1|A2|B1|B2|C1|C2"}]',
    )

    applications_count = serializers.SerializerMethodField()
    applied_applications_count = serializers.SerializerMethodField()
    application_status = serializers.SerializerMethodField()
    is_favourite = serializers.SerializerMethodField()

    employment_type_display = serializers.SerializerMethodField()
    employment_format_display = serializers.SerializerMethodField()
    salary_currency_display = serializers.SerializerMethodField()
    skill_match = serializers.SerializerMethodField()
    vacancy_skill_roadmap = serializers.SerializerMethodField()

    similarity_score = serializers.SerializerMethodField()

    address = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=30, decimal_places=15, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=30, decimal_places=15, required=False, allow_null=True)

    # Plain company logo, shown regardless of PRO branding subscription
    company_photo_url = serializers.SerializerMethodField()

    # PRO partner branding fields
    brand_page_type = serializers.SerializerMethodField()
    company_employees_count = serializers.SerializerMethodField()
    company_locations_count = serializers.SerializerMethodField()
    company_founded_year = serializers.SerializerMethodField()
    company_rating = serializers.SerializerMethodField()
    company_reviews_count = serializers.SerializerMethodField()
    company_logo_url = serializers.SerializerMethodField()
    company_tagline = serializers.SerializerMethodField()
    company_total_vacancies = serializers.SerializerMethodField()
    company_font = serializers.SerializerMethodField()
    brand_color_from = serializers.SerializerMethodField()
    brand_color_to = serializers.SerializerMethodField()
    brand_accent_color = serializers.SerializerMethodField()
    brand_text_color = serializers.SerializerMethodField()
    brand_border_color = serializers.SerializerMethodField()

    class Meta:
        model = Vacancy
        fields = [
            "id",
            "title",
            "address",
            "latitude",
            "longitude",
            "experience",
            "is_active",
            "is_demo",
            "created_by",
            "company_id",
            "company_name",
            "company_is_active",
            "recruiter_email",
            "domain",
            "domain_name",
            "employment_type",
            "employment_type_display",
            "employment_format",
            "employment_format_display",
            "applications_count",
            "applied_applications_count",
            "application_status",
            "vacancy_skill_roadmap",
            "is_favourite",
            "skill_match",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_currency_display",
            "contact_email",
            "contact_phone",
            "about_us",
            "requirements",
            "number_of_positions",
            "minimum_ai_score",
            "responsibilities",
            "additional_info",
            "expire",
            "vacancy_skills",
            "skills_data",
            "vacancy_languages",
            "languages_data",
            "created_at",
            "updated_at",
            "similarity_score",
            "company_photo_url",
            "company_logo_url",
            "company_tagline",
            "company_total_vacancies",
            "company_font",
            "brand_color_from",
            "brand_color_to",
            "brand_accent_color",
            "brand_text_color",
            "brand_border_color",
            "brand_page_type",
            "company_employees_count",
            "company_locations_count",
            "company_founded_year",
            "company_rating",
            "company_reviews_count",
        ]

        read_only_fields = [
            "id",
            "is_demo",
            "created_by",
            "company_id",
            "company_name",
            "company_is_active",
            "recruiter_email",
            "domain_name",
            "created_at",
            "updated_at",
            "vacancy_skills",
            "vacancy_languages",
            "employment_type_display",
            "employment_format_display",
            "salary_currency_display",
            "applications_count",
            "applied_applications_count",
            "application_status",
            "vacancy_skill_roadmap",
            "is_favourite",
            "skill_match",
            "company_photo_url",
            "company_logo_url",
            "company_tagline",
            "company_total_vacancies",
            "company_font",
            "brand_color_from",
            "brand_color_to",
            "brand_accent_color",
            "brand_text_color",
            "brand_border_color",
            "brand_page_type",
            "company_employees_count",
            "company_locations_count",
            "company_founded_year",
            "company_rating",
            "company_reviews_count",
        ]

    def _is_design_company(self, obj) -> bool:
        """Check if the company has an active subscription with has_design=True.
        Caches per company_id in serializer context to avoid N+1 queries."""
        cache = self.context.setdefault('_design_cache', {})
        cid = str(obj.company_id)
        if cid not in cache:
            sub = CompanySubscription.get_active(obj.company)
            cache[cid] = bool(sub and sub.has_design)
        return cache[cid]

    def get_company_photo_url(self, obj) -> str | None:
        profile = self._get_company_profile(obj)
        if profile and profile.photo:
            request = self.context.get('request')
            return request.build_absolute_uri(profile.photo.url) if request else profile.photo.url
        return None

    def get_company_logo_url(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        return self.get_company_photo_url(obj)

    def get_company_tagline(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.tagline if profile else None

    def get_company_total_vacancies(self, obj) -> int | None:
        if not self._is_design_company(obj):
            return None
        return Vacancy.objects.filter(company=obj.company, is_active=True).count()

    def get_company_font(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_font if profile else None

    def get_brand_color_from(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_color_from if profile else None

    def get_brand_color_to(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_color_to if profile else None

    def get_brand_accent_color(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_accent_color if profile else None

    def get_brand_text_color(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_text_color if profile else None

    def get_brand_border_color(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_border_color if profile else None

    def get_brand_page_type(self, obj) -> str | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.brand_page_type if profile else None

    def get_company_employees_count(self, obj) -> int | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.employees_count if profile else None

    def get_company_locations_count(self, obj) -> int | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.locations_count if profile else None

    def get_company_founded_year(self, obj) -> int | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.founded_year if profile else None

    def get_company_rating(self, obj) -> float | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return float(profile.rating) if profile and profile.rating is not None else None

    def get_company_reviews_count(self, obj) -> int | None:
        if not self._is_design_company(obj):
            return None
        profile = self._get_company_profile(obj)
        return profile.reviews_count if profile else None

    def get_similarity_score(self, obj) -> float | None:
        score = getattr(obj, "similarity_score", None)
        return round(score, 4) if score is not None else None

    @extend_schema_field(VacancySkillRoadmapSerializer)
    def get_vacancy_skill_roadmap(self, obj) -> dict | None:
        """Return vacancy-specific roadmap if candidate has an AI-rejected application."""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        if not (hasattr(request.user, "is_candidate") and request.user.is_candidate):
            return None
        candidate = self.context.get("candidate")
        if not candidate:
            return None
        roadmaps_by_vacancy = self.context.get("roadmaps_by_vacancy")
        if roadmaps_by_vacancy is not None:
            roadmap = roadmaps_by_vacancy.get(obj.id)
        else:
            # ponytail: fallback single query — views that bulk-fetch should set roadmaps_by_vacancy
            from apps.student_analytics.models import VacancySkillRoadmap
            try:
                roadmap = VacancySkillRoadmap.objects.filter(
                    application__candidate=candidate,
                    application__vacancy=obj,
                ).select_related(
                    "application__vacancy__company",
                ).prefetch_related("items__skill").first()
            except Exception:
                logger.exception("Failed to fetch vacancy_skill_roadmap for vacancy %s", obj.id)
                return None
        if not roadmap:
            return None
        lang = user_preferred_language(request.user) if request else "en"
        return VacancySkillRoadmapSerializer(roadmap, context={"language": lang}).data

    def _get_company_profile(self, obj):
        """
        Retrieve CompanyProfile via instance-level caching.

        Caches the result on the obj itself so that multiple calls
        (e.g., to_representation, get_latitude, get_longitude) share
        the same cached profile without re-querying. When the queryset
        already prefetches company__companyprofile, the .all() call is
        served from the prefetch cache and incurs zero DB queries.
        """
        cache_attr = "_company_profile_cache"
        if hasattr(obj, cache_attr):
            return getattr(obj, cache_attr)
        profiles = obj.company.companyprofile.all()
        profile = profiles[0] if profiles else None
        setattr(obj, cache_attr, profile)
        return profile

    def get_latitude(self, obj) -> float | None:
        """Get latitude from vacancy or company profile"""
        instance_latitude = getattr(obj, "latitude", None)
        if instance_latitude is not None:
            return float(instance_latitude)
        profile = self._get_company_profile(obj)
        return float(profile.latitude) if profile and profile.latitude is not None else None

    def get_longitude(self, obj) -> float | None:
        """Get longitude from vacancy or company profile"""
        instance_longitude = getattr(obj, "longitude", None)
        if instance_longitude is not None:
            return float(instance_longitude)
        profile = self._get_company_profile(obj)
        return float(profile.longitude) if profile and profile.longitude is not None else None

    def get_applications_count(self, obj) -> int:
        if hasattr(obj, "applications_count_value"):
            return obj.applications_count_value
        return obj.applications.count()

    def get_applied_applications_count(self, obj) -> int:
        """
        Get count of applications with 'Applied' status, excluding withdrawn applications.
        Only relevant for recruiter views.
        """
        if hasattr(obj, "applied_applications_count"):
            return obj.applied_applications_count

        # Fallback query if annotation not available - exclude withdrawn applications
        return (
            obj.applications.filter(status=ApplicationStatus.APPLIED)
            .exclude(status=ApplicationStatus.WITHDRAWN)
            .count()
        )

    @staticmethod
    def _normalized_language() -> str:
        language = get_request_language()
        normalized_language = (language or "").strip().lower().replace("_", "-")
        lang = normalized_language.split("-")[0] if normalized_language else "en"
        return lang if lang in {"uz", "ru", "en"} else "en"

    def get_employment_type_display(self, obj) -> str:
        lang = self._normalized_language()
        choices = get_localized_choices(lang)
        return choices["employment_type"].get(
            obj.employment_type, obj.get_employment_type_display()
        )

    def get_employment_format_display(self, obj) -> str:
        lang = self._normalized_language()
        choices = get_localized_choices(lang)
        return choices["employment_format"].get(
            obj.employment_format, obj.get_employment_format_display()
        )

    def get_salary_currency_display(self, obj) -> str:
        lang = self._normalized_language()
        choices = get_localized_choices(lang)
        return choices["salary_currency"].get(
            obj.salary_currency, obj.salary_currency
        )

    @extend_schema_field(SkillMatchSerializer)
    def get_skill_match(self, obj) -> dict | None:
        """
        Get skill match data for the current candidate.
        
        This compares the candidate's main resume skills with vacancy requirements.
        Only returns data for authenticated candidates, returns None for:
        - Unauthenticated users
        - Recruiters/Admins
        - Candidates without a main resume
        
        Uses candidate_resume from context to prevent N+1 queries.
        """
        request = self.context.get("request")
        
        # Only calculate for authenticated candidates
        if not request or not request.user.is_authenticated:
            return None
        
        if not (hasattr(request.user, "is_candidate") and request.user.is_candidate):
            return None
        
        # Get resume from context (prefetched in view)
        resume = self.context.get("candidate_resume")
        if resume is None:
            return None
        
        return SkillMatcherService.get_skill_match(obj, resume)

    def get_application_status(self, obj) -> dict:
        """
        Get application status for the current user.
        Returns application status information if user is a candidate.
        
        Uses candidate from context to prevent N+1 queries.
        """
        request = self.context.get("request")

        # Default response for unauthenticated users or non-candidates
        default_status = {"has_applied": False, "status": None, "applied_at": None}

        # Check if user is authenticated and is a candidate
        if not request or not request.user.is_authenticated:
            return default_status

        if not (hasattr(request.user, "is_candidate") and request.user.is_candidate):
            return default_status

        # Get candidate from context (set in view's get_serializer_context)
        candidate = self.context.get("candidate")
        if not candidate:
            return default_status

        # If candidate_applications dict is provided in context (bulk loaded), use it
        candidate_applications = self.context.get("candidate_applications")
        if candidate_applications is not None:
            application = candidate_applications.get(obj.id)
            if application:
                return {
                    "application_id": application.id,
                    "has_applied": True,
                    "status": application.status,
                    "status_display": application.get_status_display(),
                    "applied_at": application.applied_at,
                }
            return default_status

        # Use annotation if available (from VacancyListView)
        if hasattr(obj, "has_applied"):
            has_applied = obj.has_applied
            if not has_applied:
                return default_status

            # Get detailed application info if user has applied
            try:
                from apps.applications.models import JobApplication

                application = JobApplication.objects.get(
                    vacancy=obj, candidate=candidate
                )

                return {
                    "application_id": application.id,
                    "has_applied": True,
                    "status": application.status,
                    "applied_at": application.applied_at,
                }
            except JobApplication.DoesNotExist:
                return {"has_applied": True, "status": "unknown", "applied_at": None}

        # Fallback for views without annotation.
        # Batch-load ALL of the candidate's applications on first access
        # to prevent N+1 queries across a list of vacancies.
        cache_key = "_cached_candidate_applications"
        if not hasattr(self, cache_key):
            from apps.applications.models import JobApplication

            all_apps = JobApplication.objects.filter(
                candidate=candidate
            ).only("id", "vacancy_id", "status", "applied_at")
            setattr(
                self,
                cache_key,
                {app.vacancy_id: app for app in all_apps},
            )

        app_map = getattr(self, cache_key)
        application = app_map.get(obj.id)
        if application:
            return {
                "application_id": application.id,
                "has_applied": True,
                "status": application.status,
                "status_display": application.get_status_display(),
                "applied_at": application.applied_at,
            }
        return default_status

    def get_is_favourite(self, obj) -> bool:
        """
        Return favourite status.

        Priority:
        1. Annotated value from queryset, if present
        2. Context-provided favourite_vacancy_ids set
        3. False fallback
        """
        if hasattr(obj, "is_favourite"):
            return bool(getattr(obj, "is_favourite"))

        favourite_vacancy_ids = self.context.get("favourite_vacancy_ids")
        if favourite_vacancy_ids is not None:
            return obj.id in favourite_vacancy_ids

        return False

    def to_representation(self, instance):
        """Custom output handling for address and location fields"""
        rep = super().to_representation(instance)
        profile = self._get_company_profile(instance)

        show_inactive = self.context.get("show_inactive_skills", False)
        if not show_inactive and "vacancy_skills" in rep:
            rep["vacancy_skills"] = [
                vs for vs in rep["vacancy_skills"]
                if vs.get("skill_is_active", True)
            ]
            for vs in rep["vacancy_skills"]:
                vs.pop("skill_is_active", None)
        elif show_inactive and "vacancy_skills" in rep:
            for vs in rep["vacancy_skills"]:
                vs.pop("skill_is_active", None)
        
        # For address: show location if exists, else company profile address
        if getattr(instance, "location", None):
            rep["address"] = instance.location
        else:
            rep["address"] = profile.address if profile else None
        
        # For latitude: show vacancy latitude if exists, else company profile latitude
        instance_latitude = getattr(instance, "latitude", None)
        if instance_latitude is not None:
            rep["latitude"] = float(instance_latitude)
        else:
            rep["latitude"] = float(profile.latitude) if profile and profile.latitude is not None else None
        
        # For longitude: show vacancy longitude if exists, else company profile longitude
        instance_longitude = getattr(instance, "longitude", None)
        if instance_longitude is not None:
            rep["longitude"] = float(instance_longitude)
        else:
            rep["longitude"] = float(profile.longitude) if profile and profile.longitude is not None else None
        
        return rep

    def validate_domain(self, value):
        """
        Validate domain field.

        IMPORTANT: By this point, 'value' is already a Domain instance object,
        not an integer ID. DRF's PrimaryKeyRelatedField has already converted
        the integer ID to the Domain object.

        So we don't need to query the database again - the value is valid
        if it reached this point. We just return it.
        """
        # If domain is required and None, DRF will catch it elsewhere
        # If we have a value, it's a valid Domain instance
        return value

    @staticmethod
    def _lookup_domain_by_name(domain_name):
        """
        Look up a domain by name across all language variants (en, ru, uz).
        Raises ValidationError if no matching domain is found.
        """
        from django.db.models import Q

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

    def validate_minimum_ai_score(self, value):
        if value is not None and (value < 0 or value > 100):
            raise serializers.ValidationError(_("Minimum AI score must be between 0 and 100."))
        return value

    def validate(self, data):
        """
        Validate vacancy-level constraints and handle domain lookup by name.

        This method handles two ways to specify a domain:
        1. By ID: {"domain": 5}
        2. By name: {"domain_name": "IT"}

        Priority: domain ID takes precedence over domain_name.
        """
        # Validate salary constraints
        salary_min = data.get("salary_min")
        salary_max = data.get("salary_max")

        if salary_min and salary_max and salary_min > salary_max:
            raise serializers.ValidationError(
                "salary_min cannot be greater than salary_max"
            )

        # Handle domain lookup by name if domain wasn't provided
        # Access the original request data (initial_data contains what user sent)
        request_data = self.initial_data
        domain_name = request_data.get("domain_name")

        # If user didn't provide domain ID but provided domain_name, look it up
        if "domain" not in request_data or request_data.get("domain") is None:
            if domain_name:
                domain = self._lookup_domain_by_name(domain_name)
                data["domain"] = domain

        return data

    def validate_skills_data(self, value):
        """Validate the skills data format and ensure skills exist."""
        if not value:
            return value

        skill_ids = []
        for skill_data in value:
            if "skill_id" not in skill_data:
                raise serializers.ValidationError(
                    "Each skill must have a 'skill_id' field"
                )
            skill_ids.append(skill_data["skill_id"])

        # Only approved (is_active=True) skills may be attached to a vacancy.
        # Pending skills can still be rejected or merged as a duplicate by the
        # nightly AI validation job, which cascade-deletes the Skill row and
        # would silently drop the requirement from the vacancy otherwise.
        existing_skills = Skill.objects.filter(is_active=True).in_bulk(skill_ids)
        validated_skills = []

        for skill_data in value:
            skill_id = skill_data["skill_id"]
            skill = existing_skills.get(skill_id)
            if skill is None:
                raise serializers.ValidationError(
                    f"Skill with ID {skill_id} does not exist or is not yet approved"
                )
            if not localized_skill_name(skill):
                raise serializers.ValidationError(
                    _("Skill with ID %(skill_id)s has an empty name")
                     % {"skill_id": skill_id}
                )

            proficiency_level = skill_data.get("proficiency_level", "UNDEFINED")
            valid_levels = [
                "UNDEFINED",
                "BEGINNER",
                "INTERMEDIATE",
                "ADVANCED",
                "EXPERT",
            ]
            if proficiency_level not in valid_levels:
                raise serializers.ValidationError(
                    f"Invalid proficiency level: {proficiency_level}"
                )

            minimum_years = skill_data.get("minimum_years", 0)
            if minimum_years < 0:
                raise serializers.ValidationError(_("minimum_years cannot be negative"))

            validated_skill = {
                "skill": skill,
                "is_required": skill_data.get("is_required", True),
                "minimum_years": minimum_years,
                "proficiency_level": proficiency_level,
            }

            validated_skills.append(validated_skill)

        return validated_skills

    def create(self, validated_data):
        skills_data = validated_data.pop("skills_data", [])
        languages_data = validated_data.pop("languages_data", [])
        address = validated_data.pop("address", None)
        
        if address:
            validated_data["location"] = address
        vacancy = super().create(validated_data)
        self._create_vacancy_skills(vacancy, skills_data)
        self._create_vacancy_languages(vacancy, languages_data)
        return vacancy

    def update(self, instance, validated_data):
        skills_data = validated_data.pop("skills_data", None)
        languages_data = validated_data.pop("languages_data", None)
        address = validated_data.pop("address", None)
        if address:
            validated_data["location"] = address
        
        vacancy = super().update(instance, validated_data)

        if skills_data is not None:
            vacancy.vacancyskill_set.all().delete()
            self._create_vacancy_skills(vacancy, skills_data)

        if languages_data is not None:
            vacancy.vacancy_languages.all().delete()
            self._create_vacancy_languages(vacancy, languages_data)

        return vacancy

    def _create_vacancy_skills(self, vacancy, skills_data):
        if not skills_data:
            return

        vacancy_skills = []
        for skill_data in skills_data:
            vacancy_skill = VacancySkill(
                vacancy=vacancy,
                skill=skill_data["skill"],
                is_required=skill_data["is_required"],
                minimum_years=skill_data["minimum_years"],
                proficiency_level=skill_data["proficiency_level"],
            )
            vacancy_skills.append(vacancy_skill)

        VacancySkill.objects.bulk_create(vacancy_skills)

    def validate_languages_data(self, value):
        """Validate the languages data format and ensure languages exist."""
        if not value:
            return value

        valid_levels = [choice[0] for choice in LanguageProficiencyLevel.choices]
        validated_languages = []

        for lang_data in value:
            if "language_id" not in lang_data:
                raise serializers.ValidationError(
                    _("Each language entry must have a 'language_id' field.")
                )

            try:
                language = Language.objects.get(id=lang_data["language_id"])
            except (Language.DoesNotExist, ValueError, TypeError):
                raise serializers.ValidationError(
                    _("Language with ID %(id)s does not exist.") % {"id": lang_data["language_id"]}
                )

            level = lang_data.get("level")
            if not level:
                raise serializers.ValidationError(
                    _("Each language entry must have a 'level' field.")
                )
            if level not in valid_levels:
                raise serializers.ValidationError(
                    _("Invalid proficiency level '%(level)s'. Valid levels: %(valid)s.")
                    % {"level": level, "valid": ", ".join(valid_levels)}
                )

            validated_languages.append({"language": language, "level": level})

        return validated_languages

    def validate_about_us(self, value):
        return validate_safe_html(value)

    def validate_requirements(self, value):
        return validate_safe_html(value)

    def validate_responsibilities(self, value):
        return validate_safe_html(value)

    def validate_additional_info(self, value):
        return validate_safe_html(value)

    def _create_vacancy_languages(self, vacancy, languages_data):
        if not languages_data:
            return

        vacancy_languages = [
            VacancyLanguage(
                vacancy=vacancy,
                language=lang_data["language"],
                level=lang_data["level"],
            )
            for lang_data in languages_data
        ]
        VacancyLanguage.objects.bulk_create(vacancy_languages)
