"""
AI action endpoints.

GET  /api/v1/ai/validate/?status=passive_skills  — list passive skills (admin)
POST /api/v1/ai/validate/                         — run AI action (skill validation or vacancy creation)
"""

import logging

from django.http import Http404
from django.utils.translation import gettext as _
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ai.serializers import (
    AIActionRequestSerializer,
    PassiveSkillListSerializer,
)
from apps.ai.services.groq_client import GroqClient
from apps.ai.services.skill_validator import validate_passive_skills
from apps.ai.services.vacancy_creator import (
    create_vacancy_from_text,
    fetch_url_content,
)
from apps.ai.services.template_drafter import draft_template_text
from apps.authentication.models import Recruiter
from apps.skills.models import Skill
from apps.subscriptions.permissions import (
    get_cached_company,
    get_cached_features,
    get_cached_recruiter,
    set_cached_recruiter,
)
from apps.subscriptions.services import (
    FEATURE_AI_TEMPLATE_GENERATION,
    SubscriptionService,
)
from apps.vacancies.serializers import VacancySerializer
from core.responses import APIResponse
from utils.prompt_sanitizer import detect_prompt_injection

logger = logging.getLogger(__name__)


class AIActionAPIView(APIView):
    """
    Unified endpoint for AI-powered actions.

    GET  — List passive skills (admin only, requires ?status=passive_skills).
    POST — Run AI action:
           - status=passive_skills: validate pending skills (admin only)
           - status=create_vacancy:  create a vacancy from URL or body text (recruiter only)
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai_action"

    # ------------------------------------------------------------------
    # GET — list passive skills (admin only)
    # ------------------------------------------------------------------

    def get(self, request, *args, **kwargs):
        status_param = request.query_params.get("status", "").strip()

        # Recruiter: remaining AI template generations this month (for the button)
        if status_param == "ai_template_quota":
            if not request.user.is_recruiter:
                return APIResponse.forbidden(
                    message=_("Only recruiters can view the template quota.")
                )
            features = get_cached_features(request)
            has_feature = FEATURE_AI_TEMPLATE_GENERATION in features
            company = get_cached_company(request)
            if not has_feature or company is None:
                return APIResponse.success(
                    data={"enabled": has_feature, "remaining": 0, "max_generations_per_month": 0},
                    message=_("Template quota retrieved."),
                )
            limit = SubscriptionService.check_template_ai_limit(company, features=features)
            return APIResponse.success(
                data={
                    "enabled": True,
                    "remaining": limit["remaining"],
                    "max_generations_per_month": limit["max_generations_per_month"],
                    "current_usage": limit["current_usage"],
                },
                message=_("Template quota retrieved."),
            )

        if not request.user.is_staff:
            return APIResponse.forbidden(
                message=_("Only administrators can list passive skills.")
            )

        if not status_param:
            return APIResponse.validation_error(
                message=_("The 'status' query parameter is required."),
                field_errors={
                    "status": _(
                        "This parameter is mandatory. Supported value: 'passive_skills'."
                    )
                },
            )

        if status_param == "passive_skills":
            passive = (
                Skill.objects.filter(is_active=False)
                .only("id", "name", "name_ru", "name_uz", "description", "created_at")
                .order_by("name")
            )
            serializer = PassiveSkillListSerializer(passive, many=True)
            return APIResponse.success(
                data=serializer.data,
                message=_("Passive skills retrieved successfully."),
            )

        return APIResponse.validation_error(
            message=_("Invalid status parameter."),
            field_errors={
                "status": _("Only 'passive_skills' is currently supported.")
            },
        )

    # ------------------------------------------------------------------
    # POST — run AI action
    # ------------------------------------------------------------------

    def post(self, request, *args, **kwargs):
        serializer = AIActionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(
                field_errors=serializer.errors,
            )

        status_value = serializer.validated_data["status"]
        ai_model = serializer.validated_data["ai_model"]

        # --- role check ---
        if status_value == "passive_skills" and not request.user.is_staff:
            return APIResponse.forbidden(
                message=_("Only administrators can validate skills.")
            )

        if status_value == "create_vacancy" and not request.user.is_recruiter:
            return APIResponse.forbidden(
                message=_("Only recruiters can create vacancies.")
            )

        if status_value == "draft_template":
            if not request.user.is_recruiter:
                return APIResponse.forbidden(
                    message=_("Only recruiters can draft templates.")
                )
            # Subscription gate — admin assigns this feature per plan.
            if FEATURE_AI_TEMPLATE_GENERATION not in get_cached_features(request):
                return APIResponse.forbidden(
                    message=_(
                        "Your current subscription plan does not include "
                        "AI template generation. Upgrade your plan to use it."
                    )
                )

        # --- AI client ---
        try:
            client = self._get_ai_client(ai_model)
        except ValueError as exc:
            return APIResponse.server_error(
                message=str(exc),
                details=_(
                    "The selected AI provider is not properly configured. "
                    "Please check the API key in settings."
                ),
            )

        # --- dispatch by status ---
        if status_value == "passive_skills":
            return self._handle_skill_validation(client)

        if status_value == "draft_template":
            return self._handle_draft_template(request, serializer, client)

        return self._handle_create_vacancy(request, serializer, client)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_skill_validation(self, client):
        try:
            result = validate_passive_skills(client)
        except Exception as exc:
            logger.exception("Skill validation failed")
            return APIResponse.server_error(
                message=_("AI validation failed."),
                details=str(exc),
            )

        return APIResponse.success(
            data=result,
            message=result.get("message", _("Validation completed.")),
        )

    def _handle_create_vacancy(self, request, serializer, client):
        try:
            recruiter, company = self._get_recruiter_and_company(request)
        except Http404 as exc:
            return APIResponse.not_found(message=str(exc))
        except PermissionDenied as exc:
            return APIResponse.forbidden(message=str(exc))

        vacancy_url = serializer.validated_data.get("vacancy_url")
        vacancy_body = serializer.validated_data.get("vacancy_body")

        # Resolve source text
        source_text = None
        if vacancy_url:
            try:
                source_text = fetch_url_content(vacancy_url)
            except Exception as exc:
                logger.exception("Failed to fetch URL: %s", vacancy_url)
                return APIResponse.server_error(
                    message=_("Failed to fetch vacancy from the provided URL."),
                    details=str(exc),
                )
        elif vacancy_body:
            source_text = vacancy_body

        # Prompt injection check
        if source_text:
            injection_match = detect_prompt_injection(source_text)
            if injection_match:
                return APIResponse.validation_error(
                    message=_(
                        "Your input appears to contain prompt injection patterns. "
                        "Please revise and try again."
                    )
                )

        # AI extraction + vacancy creation
        try:
            vacancy = create_vacancy_from_text(client, source_text, recruiter, company)
        except Exception as exc:
            logger.exception("AI vacancy creation failed")
            return APIResponse.server_error(
                message=_("Vacancy creation failed."),
                details=str(exc),
            )

        return APIResponse.created(
            data=VacancySerializer(vacancy).data,
            message=_("Vacancy created successfully via AI."),
        )

    def _handle_draft_template(self, request, serializer, client):
        try:
            _recruiter, company = self._get_recruiter_and_company(request)
        except Http404 as exc:
            return APIResponse.not_found(message=str(exc))
        except PermissionDenied as exc:
            return APIResponse.forbidden(message=str(exc))

        section = serializer.validated_data["template_section"]
        instruction = (serializer.validated_data.get("instruction") or "").strip()
        locale = (serializer.validated_data.get("locale") or "ru").strip() or "ru"

        # --- monthly usage limit ---
        features = get_cached_features(request)
        limit = SubscriptionService.check_template_ai_limit(company, features=features)
        if not limit["allowed"]:
            return APIResponse.forbidden(
                message=_(
                    "AI template generation limit reached (%(current)d/%(max)d) "
                    "for this month. Upgrade your plan for more."
                ) % {
                    "current": limit["current_usage"],
                    "max": limit["max_generations_per_month"],
                },
                details={
                    "remaining": limit["remaining"],
                    "max_generations_per_month": limit["max_generations_per_month"],
                    "current_usage": limit["current_usage"],
                },
            )

        # Prompt injection check on the free-text instruction
        if instruction:
            if detect_prompt_injection(instruction):
                return APIResponse.validation_error(
                    message=_(
                        "Your instruction appears to contain prompt injection "
                        "patterns. Please revise and try again."
                    )
                )

        text = None
        last_error = None
        for model in ("groq",):
            try:
                model_client = self._get_ai_client(model)
                text = draft_template_text(
                    model_client,
                    section=section,
                    company_name=company.name,
                    locale=locale,
                    instruction=instruction,
                )
                break
            except Exception as exc:  # noqa: BLE001 — try the next provider
                last_error = exc
                logger.warning("AI template drafting via '%s' failed: %s", model, exc)

        if text is None:
            logger.exception("AI template drafting failed on all providers")
            return APIResponse.server_error(
                message=_("Template drafting failed."),
                details=str(last_error) if last_error else "",
            )

        # Count this successful generation against the monthly quota
        SubscriptionService.consume_template_ai(company, limit["feature"])
        remaining = max(0, limit["remaining"] - 1)

        return APIResponse.success(
            data={
                "text": text,
                "remaining": remaining,
                "max_generations_per_month": limit["max_generations_per_month"],
            },
            message=_("Template drafted successfully."),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_recruiter_and_company(self, request):
        """Extract recruiter and company from the authenticated user."""
        user = request.user

        if not user.is_recruiter:
            raise PermissionDenied("Only recruiters can create vacancies")

        recruiter = get_cached_recruiter(request)
        if recruiter is None:
            try:
                recruiter = Recruiter.objects.select_related("company").get(
                    email=user.email
                )
                set_cached_recruiter(request, recruiter)
            except Recruiter.DoesNotExist:
                raise Http404("Recruiter not found")

        if not recruiter.company:
            raise PermissionDenied(
                _("Recruiter must be associated with a company to create vacancies")
            )

        if not recruiter.company.is_active:
            raise PermissionDenied(
                _("Your company account is not active. Please contact support.")
            )

        return recruiter, recruiter.company

    @staticmethod
    def _get_ai_client(ai_model: str):
        if ai_model == "groq":
            return GroqClient()
        raise ValueError(_("Unknown AI model: %s") % ai_model)


# Module-level view instance (follows project convention)
ai_action_view = AIActionAPIView.as_view()
