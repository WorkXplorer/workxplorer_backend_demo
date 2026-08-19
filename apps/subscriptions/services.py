"""
Subscription service layer.

Centralizes all subscription business logic so that views, serializers,
and other apps only need to call service methods instead of duplicating logic.

Key responsibilities:
- Checking feature access for companies
- Checking recruiter seat limits during company registration
- Creating default (free) subscriptions for new companies/candidates
- Managing seat assignments
"""

import logging

from django.db import transaction, IntegrityError
from django.utils.translation import gettext as _

from apps.subscriptions.models import (
    SubscriptionPlan,
    CompanySubscription,
    CandidateSubscription,
    SubscriptionSeatAssignment,
    PlanFeature,
)

logger = logging.getLogger(__name__)


# Sentinel to distinguish "argument not provided" from "cached as None"
_NOT_PROVIDED = object()


# ──────────────────────────────────────────────────────────
# Plan slugs — single source of truth for referencing plans
# ──────────────────────────────────────────────────────────

COMPANY_FREE_PLAN_SLUG = "company-free"
COMPANY_BASIC_PLAN_SLUG = "company-basic"
COMPANY_PRO_PLAN_SLUG = "company-pro"
CANDIDATE_FREE_PLAN_SLUG = "candidate-free"
CANDIDATE_BASIC_PLAN_SLUG = "candidate-basic"
CANDIDATE_PRO_PLAN_SLUG = "candidate-pro"

# ──────────────────────────────────────────────────────────
# Feature codes — used for permission checks
# ──────────────────────────────────────────────────────────

FEATURE_COMPANY_ANALYTICS = "company_analytics"
FEATURE_FULL_ANALYTICS = "full_analytics"
FEATURE_HEADHUNTING_ACCESS = "headhunting_access"
FEATURE_VACANCY_LIMIT = "vacancy_limit"
FEATURE_TEMPLATE_LIMIT = "template_limit"
FEATURE_REASON_LIMIT = FEATURE_TEMPLATE_LIMIT  # backward compatibility alias
FEATURE_AI_RESUME_GENERATION = "ai_resume_generation"
FEATURE_ANALYTICS_REGENERATION = "analytics_regeneration"
FEATURE_AI_TEMPLATE_GENERATION = "ai_template_generation"

# ──────────────────────────────────────────────────────────
# Default limits per plan (used as fallback when no
# subscription / PlanFeature configuration exists)
# ──────────────────────────────────────────────────────────

DEFAULT_VACANCY_LIMITS = {
    "company-free": {"max_active_vacancies": 3, "max_expire_days": 30},
    "company-basic": {"max_active_vacancies": 5, "max_expire_days": 90},
    "company-pro": {"max_active_vacancies": 10, "max_expire_days": 180},
}

DEFAULT_TEMPLATE_LIMITS = {
    "company-free": {"max_reasons": 2},
    "company-basic": {"max_reasons": 5},
    "company-pro": {"max_reasons": 10},
}
DEFAULT_REASON_LIMITS = DEFAULT_TEMPLATE_LIMITS  # backward compatibility alias

DEFAULT_AI_GENERATION_LIMITS = {
    "candidate-free": {"max_generations_per_month": 1},
    "candidate-basic": {"max_generations_per_month": 10},
    "candidate-pro": {"max_generations_per_month": 30},
}

DEFAULT_ANALYTICS_REGENERATION_LIMITS = {
    "candidate-free": {"max_regenerations_per_month": 30},
    "candidate-basic": {"max_regenerations_per_month": 50},
    "candidate-pro": {"max_regenerations_per_month": 100},
}

# Monthly limit for AI template drafting per company plan. Used as a
# fallback when the PlanFeature configuration doesn't specify it.
DEFAULT_TEMPLATE_AI_LIMITS = {
    "company-free": {"max_generations_per_month": 0},
    "company-basic": {"max_generations_per_month": 20},
    "company-pro": {"max_generations_per_month": 100},
}
DEFAULT_TEMPLATE_AI_LIMIT_FALLBACK = {"max_generations_per_month": 10}


class SubscriptionService:
    """
    Service class for all subscription-related business logic.

    All methods are static/classmethod so the service can be used
    without instantiation.
    """

    # ─── Default plan retrieval ───────────────────────────

    @staticmethod
    def get_default_company_plan() -> SubscriptionPlan | None:
        """
        Get the default (free) subscription plan for companies.
        Returns None if the plan doesn't exist yet (e.g., before initial data load).
        """
        try:
            return SubscriptionPlan.objects.get(
                slug=COMPANY_FREE_PLAN_SLUG,
                is_active=True,
            )
        except SubscriptionPlan.DoesNotExist:
            logger.warning(
                "Default company plan '%s' not found. "
                "Run the seed_subscriptions management command.",
                COMPANY_FREE_PLAN_SLUG,
            )
            return None

    @staticmethod
    def get_company_free_plan() -> SubscriptionPlan | None:
        """
        Get the free company plan regardless of active status.
        Used for limit checks so values always come from the database.
        """
        try:
            return SubscriptionPlan.objects.get(
                slug=COMPANY_FREE_PLAN_SLUG,
            )
        except SubscriptionPlan.DoesNotExist:
            logger.warning(
                "Company free plan '%s' not found. "
                "Run the seed_subscriptions management command.",
                COMPANY_FREE_PLAN_SLUG,
            )
            return None

    @staticmethod
    def get_default_candidate_plan() -> SubscriptionPlan | None:
        """Get the default (free) subscription plan for candidates."""
        try:
            return SubscriptionPlan.objects.get(
                slug=CANDIDATE_FREE_PLAN_SLUG,
                is_active=True,
            )
        except SubscriptionPlan.DoesNotExist:
            logger.warning(
                "Default candidate plan '%s' not found. "
                "Run the seed_subscriptions management command.",
                CANDIDATE_FREE_PLAN_SLUG,
            )
            return None

    # ─── Subscription creation ────────────────────────────

    @staticmethod
    @transaction.atomic
    def create_company_subscription(company, plan=None, expire_existing=True):
        """
        Create a subscription for a company.

        If no plan is given, the default free plan is used.
        Any existing active subscription is marked as expired.

        Args:
            company: The Company instance.
            plan: Optional SubscriptionPlan. Defaults to free plan.
            expire_existing: Whether to expire previously active subscriptions.

        Returns:
            The created CompanySubscription, or None if no plan available.
        """
        if plan is None:
            plan = SubscriptionService.get_default_company_plan()
            if plan is None:
                return None

        # Deactivate any existing active subscription
        if expire_existing:
            CompanySubscription.objects.filter(
                company=company,
                status=CompanySubscription.Status.ACTIVE,
            ).update(status=CompanySubscription.Status.EXPIRED)

        subscription = CompanySubscription.objects.create(
            company=company,
            plan=plan,
            status=CompanySubscription.Status.ACTIVE,
        )

        logger.info(
            "Created %s subscription for company '%s' (ID: %s)",
            plan.name,
            company.name,
            company.id,
        )
        return subscription

    @staticmethod
    @transaction.atomic
    def create_candidate_subscription(candidate, plan=None):
        """
        Create a subscription for a candidate.

        If no plan is given, the default free plan is used.

        Args:
            candidate: The Candidate instance.
            plan: Optional SubscriptionPlan. Defaults to free plan.

        Returns:
            The created CandidateSubscription, or None if no plan available.
        """
        if plan is None:
            plan = SubscriptionService.get_default_candidate_plan()
            if plan is None:
                return None

        # Deactivate any existing active subscription
        CandidateSubscription.objects.filter(
            candidate=candidate,
            status=CandidateSubscription.Status.ACTIVE,
        ).update(status=CandidateSubscription.Status.EXPIRED)

        subscription = CandidateSubscription.objects.create(
            candidate=candidate,
            plan=plan,
            status=CandidateSubscription.Status.ACTIVE,
        )

        logger.info(
            "Created %s subscription for candidate '%s' (ID: %s)",
            plan.name,
            candidate.email,
            candidate.id,
        )
        return subscription

    # ─── Plan limit checks ────────────────────────────────

    @staticmethod
    def get_company_plan(company) -> SubscriptionPlan | None:
        """
        Get the current plan for a company from its active subscription.
        Returns None if no active subscription exists.
        """
        subscription = CompanySubscription.get_active(company)
        if subscription:
            return subscription.plan
        return None

    @staticmethod
    def get_recruiter_limits(company, plan_override: SubscriptionPlan | None = None) -> dict | None:
        """
        Get the recruiter limits for a company based on its current plan.

        Returns:
            dict with keys:
            - 'max_admins': int
            - 'max_recruiters': int
            - 'plan_name': str

            Falls back to the free plan stored in the database if no subscription exists.
            Returns None if the free plan is not configured.
        """
        plan = plan_override
        if plan is None and company is not None:
            plan = SubscriptionService.get_company_plan(company)
        if plan:
            return {
                "max_admins": plan.max_admins,
                "max_recruiters": plan.max_recruiters,
                "plan_name": plan.name,
            }

        plan = SubscriptionService.get_company_free_plan()
        if plan is None:
            return None

        return {
            "max_admins": plan.max_admins,
            "max_recruiters": plan.max_recruiters,
            "plan_name": plan.name,
        }

    @staticmethod
    def check_recruiter_limit(
        company,
        num_admins: int,
        num_recruiters: int,
        plan_override: SubscriptionPlan | None = None,
    ) -> dict:
        """
        Check if the **total** number of admins and recruiters is within
        the company's subscription limits.

        Designed for **initial company registration** where the provided
        counts represent the complete roster for the new company (no
        existing users to account for).  For an existing company that
        already has recruiters you should add the current seat count to
        ``num_admins`` / ``num_recruiters`` before calling this method,
        or use :py:meth:`assign_seat` which enforces limits through
        :py:meth:`get_seat_usage`.

        Args:
            company: The Company instance (can be None for new companies).
            num_admins: Total number of admin-level users (including
                existing ones if applicable).
            num_recruiters: Total number of recruiter-level users
                (including existing ones if applicable).

        Returns:
            dict with keys:
            - 'allowed': bool
            - 'max_admins': int
            - 'max_recruiters': int
            - 'errors': list of error messages (empty if allowed)
        """
        limits = SubscriptionService.get_recruiter_limits(
            company,
            plan_override=plan_override,
        )
        if limits is None:
            return {
                "allowed": False,
                "max_admins": 0,
                "max_recruiters": 0,
                "errors": [
                    _(
                        "Default company subscription plan is not configured. "
                        "Please contact support."
                    )
                ],
            }

        errors = []
        if num_admins > limits["max_admins"]:
            errors.append(
                _(
                    "The %(plan)s plan allows a maximum of "
                    "%(max)d admin(s). You requested %(requested)d."
                ) % {
                    "plan": limits["plan_name"],
                    "max": limits["max_admins"],
                    "requested": num_admins,
                }
            )
        if num_recruiters > limits["max_recruiters"]:
            errors.append(
                _(
                    "The %(plan)s plan allows a maximum of "
                    "%(max)d recruiter(s). You requested %(requested)d."
                ) % {
                    "plan": limits["plan_name"],
                    "max": limits["max_recruiters"],
                    "requested": num_recruiters,
                }
            )

        return {
            "allowed": len(errors) == 0,
            "max_admins": limits["max_admins"],
            "max_recruiters": limits["max_recruiters"],
            "errors": errors,
        }

    # ─── Feature access checks ────────────────────────────

    @staticmethod
    def company_has_feature(company, feature_code: str) -> bool:
        """
        Check if a company's active subscription includes a specific feature.

        Args:
            company: The Company instance.
            feature_code: The feature code to check (e.g., 'headhunting_access').

        Returns:
            True if the company has an active subscription with the feature.
        """
        subscription = CompanySubscription.get_active(company)
        if subscription is None:
            return False
        return subscription.has_feature(feature_code)

    @staticmethod
    def recruiter_has_feature(user, feature_code: str) -> bool:
        """
        Check if a recruiter's company has a feature through their subscription.

        Handles both ``Recruiter`` instances (which have ``.company`` directly)
        and ``CustomUser`` instances (where the company must be resolved via a
        DB query on the Recruiter table, because Django's multi-table
        inheritance does not automatically hydrate child fields on the parent).

        Args:
            user: A CustomUser or Recruiter instance.
            feature_code: The feature code to check.

        Returns:
            True if the recruiter's company subscription includes the feature.
        """
        from apps.authentication.models import Recruiter

        company = getattr(user, "company", None)
        if company is None:
            # user is probably a CustomUser — resolve the Recruiter row.
            try:
                recruiter = Recruiter.objects.select_related("company").get(
                    pk=user.pk
                )
                company = recruiter.company
            except Recruiter.DoesNotExist:
                return False
        if company is None:
            return False
        return SubscriptionService.company_has_feature(company, feature_code)

    @staticmethod
    def candidate_has_feature(candidate, feature_code: str) -> bool:
        """
        Check if a candidate's active subscription includes a specific feature.

        Args:
            candidate: The Candidate instance.
            feature_code: The feature code to check.

        Returns:
            True if the candidate has an active subscription with the feature.
        """
        subscription = CandidateSubscription.get_active(candidate)
        if subscription is None:
            return False
        return subscription.has_feature(feature_code)

    # ─── AI Generation limit checks ─────────────────────

    @staticmethod
    def _extract_ai_gen_config(plan, features=None):
        """
        Extract AI generation configuration from a pre-fetched features
        dict or from the PlanFeature table.
        """
        pf = None
        if features is not None:
            pf = features.get(FEATURE_AI_RESUME_GENERATION)
        else:
            try:
                pf = PlanFeature.objects.get(
                    plan=plan,
                    feature__code=FEATURE_AI_RESUME_GENERATION,
                    is_enabled=True,
                )
            except PlanFeature.DoesNotExist:
                logger.warning(
                    "Plan '%s' is missing '%s' feature configuration. "
                    "Using defaults for AI generation limits.",
                    plan.name,
                    FEATURE_AI_RESUME_GENERATION,
                )

        fallback = DEFAULT_AI_GENERATION_LIMITS.get(
            plan.slug, DEFAULT_AI_GENERATION_LIMITS[CANDIDATE_FREE_PLAN_SLUG]
        )

        if pf is not None:
            config = pf.configuration or {}
            return {
                "max_generations_per_month": config.get(
                    "max_generations_per_month",
                    fallback["max_generations_per_month"],
                ),
                "plan_name": plan.name,
            }

        return {**fallback, "plan_name": plan.name}

    @staticmethod
    def get_ai_generation_limits(candidate, *, subscription=_NOT_PROVIDED, features=None) -> dict:
        """
        Get AI resume generation limits for a candidate based on their
        active subscription.
        """
        if subscription is _NOT_PROVIDED:
            subscription = CandidateSubscription.get_active(candidate)
        if subscription is None:
            defaults = DEFAULT_AI_GENERATION_LIMITS[CANDIDATE_FREE_PLAN_SLUG]
            return {**defaults, "plan_name": "Free (default)"}

        return SubscriptionService._extract_ai_gen_config(
            subscription.plan, features
        )

    @staticmethod
    def check_ai_generation_limit(candidate, *, subscription=_NOT_PROVIDED, features=None) -> dict:
        """
        Check if the candidate can perform an AI resume generation
        based on their current monthly usage vs. plan limits.
        """
        from datetime import date
        from apps.subscriptions.models import CandidateFeatureUsage, SubscriptionFeature

        limits = SubscriptionService.get_ai_generation_limits(
            candidate, subscription=subscription, features=features
        )

        feature = SubscriptionFeature.objects.filter(
            code=FEATURE_AI_RESUME_GENERATION,
            is_active=True,
        ).first()

        current_usage = 0
        if feature:
            month_start = date.today().replace(day=1)
            usage_record = CandidateFeatureUsage.objects.filter(
                candidate=candidate,
                feature=feature,
                usage_month=month_start,
            ).first()
            if usage_record:
                current_usage = usage_record.usage_count

        max_allowed = limits["max_generations_per_month"]

        if current_usage >= max_allowed:
            return {
                "allowed": False,
                "max_generations_per_month": max_allowed,
                "current_usage": current_usage,
                "plan_name": limits["plan_name"],
                "error": _(
                    "AI resume generation limit reached (%(current)d/%(max)d). "
                    "Upgrade your plan for more generations."
                ) % {"current": current_usage, "max": max_allowed},
            }

        return {
            "allowed": True,
            "max_generations_per_month": max_allowed,
            "current_usage": current_usage,
            "plan_name": limits["plan_name"],
            "error": None,
        }

    # ─── Analytics Regeneration limit checks ──────────────

    # ─── AI template drafting limit (company) ─────────────

    @staticmethod
    def check_template_ai_limit(company, *, features=None) -> dict:
        """
        Check whether a company can draft another AI template this month.

        The per-month limit is read from the AI-template-generation
        PlanFeature ``configuration`` (key ``max_generations_per_month``),
        falling back to plan-slug defaults. Returns usage details used both
        for enforcement and to display the remaining count on the button.
        """
        from datetime import date
        from apps.subscriptions.models import (
            CompanyFeatureUsage,
            SubscriptionFeature,
        )

        subscription = CompanySubscription.get_active(company)
        plan_name = subscription.plan.name if subscription else "Free (default)"

        # Resolve the monthly limit
        max_allowed = DEFAULT_TEMPLATE_AI_LIMIT_FALLBACK["max_generations_per_month"]
        pf = None
        if features is not None:
            pf = features.get(FEATURE_AI_TEMPLATE_GENERATION)
        elif subscription is not None:
            pf = PlanFeature.objects.filter(
                plan=subscription.plan,
                feature__code=FEATURE_AI_TEMPLATE_GENERATION,
                is_enabled=True,
            ).first()

        if subscription is not None:
            fallback = DEFAULT_TEMPLATE_AI_LIMITS.get(
                subscription.plan.slug, DEFAULT_TEMPLATE_AI_LIMIT_FALLBACK
            )
            max_allowed = fallback["max_generations_per_month"]

        if pf is not None and isinstance(pf.configuration, dict):
            max_allowed = pf.configuration.get("max_generations_per_month", max_allowed)

        feature = SubscriptionFeature.objects.filter(
            code=FEATURE_AI_TEMPLATE_GENERATION,
            is_active=True,
        ).first()

        current_usage = CompanyFeatureUsage.current_usage(company, feature, date.today())
        remaining = max(0, max_allowed - current_usage)

        return {
            "allowed": current_usage < max_allowed,
            "max_generations_per_month": max_allowed,
            "current_usage": current_usage,
            "remaining": remaining,
            "plan_name": plan_name,
            "feature": feature,
        }

    @staticmethod
    def consume_template_ai(company, feature):
        """Increment the company's monthly AI-template usage counter."""
        from apps.subscriptions.models import CompanyFeatureUsage

        if feature is None:
            return
        CompanyFeatureUsage.increment_usage(company, feature)

    @staticmethod
    def _extract_analytics_regeneration_config(plan, features=None):
        """
        Extract analytics regeneration configuration from a pre-fetched
        features dict or from the PlanFeature table.
        """
        pf = None
        if features is not None:
            pf = features.get(FEATURE_ANALYTICS_REGENERATION)
        else:
            try:
                pf = PlanFeature.objects.get(
                    plan=plan,
                    feature__code=FEATURE_ANALYTICS_REGENERATION,
                    is_enabled=True,
                )
            except PlanFeature.DoesNotExist:
                logger.warning(
                    "Plan '%s' is missing '%s' feature configuration. "
                    "Using defaults for analytics regeneration limits.",
                    plan.name,
                    FEATURE_ANALYTICS_REGENERATION,
                )

        fallback = DEFAULT_ANALYTICS_REGENERATION_LIMITS.get(
            plan.slug,
            DEFAULT_ANALYTICS_REGENERATION_LIMITS[CANDIDATE_FREE_PLAN_SLUG],
        )

        if pf is not None:
            config = pf.configuration or {}
            return {
                "max_regenerations_per_month": config.get(
                    "max_regenerations_per_month",
                    fallback["max_regenerations_per_month"],
                ),
                "plan_name": plan.name,
            }

        return {**fallback, "plan_name": plan.name}

    @staticmethod
    def get_analytics_regeneration_limits(
        candidate, *, subscription=_NOT_PROVIDED, features=None
    ) -> dict:
        """
        Get analytics regeneration limits for a candidate based on their
        active subscription.
        """
        if subscription is _NOT_PROVIDED:
            subscription = CandidateSubscription.get_active(candidate)
        if subscription is None:
            defaults = DEFAULT_ANALYTICS_REGENERATION_LIMITS[CANDIDATE_FREE_PLAN_SLUG]
            return {**defaults, "plan_name": "Free (default)"}

        return SubscriptionService._extract_analytics_regeneration_config(
            subscription.plan, features
        )

    @staticmethod
    def check_analytics_regeneration_limit(
        candidate, *, subscription=_NOT_PROVIDED, features=None
    ) -> dict:
        """
        Check if the candidate can regenerate analytics based on their
        current monthly usage vs. plan limits.
        """
        from datetime import date
        from apps.subscriptions.models import CandidateFeatureUsage, SubscriptionFeature

        limits = SubscriptionService.get_analytics_regeneration_limits(
            candidate, subscription=subscription, features=features
        )

        feature = SubscriptionFeature.objects.filter(
            code=FEATURE_ANALYTICS_REGENERATION,
            is_active=True,
        ).first()

        current_usage = 0
        if feature:
            month_start = date.today().replace(day=1)
            usage_record = CandidateFeatureUsage.objects.filter(
                candidate=candidate,
                feature=feature,
                usage_month=month_start,
            ).first()
            if usage_record:
                current_usage = usage_record.usage_count

        max_allowed = limits["max_regenerations_per_month"]

        if current_usage >= max_allowed:
            return {
                "allowed": False,
                "max_regenerations_per_month": max_allowed,
                "current_usage": current_usage,
                "plan_name": limits["plan_name"],
                "error": _(
                    "Analytics regeneration limit reached (%(current)d/%(max)d). "
                    "Upgrade your plan for more regenerations."
                ) % {"current": current_usage, "max": max_allowed},
            }

        return {
            "allowed": True,
            "max_regenerations_per_month": max_allowed,
            "current_usage": current_usage,
            "plan_name": limits["plan_name"],
            "error": None,
        }

    @staticmethod
    def record_analytics_regeneration(candidate):
        """Record an analytics regeneration usage for the current month."""
        from apps.subscriptions.models import CandidateFeatureUsage, SubscriptionFeature

        feature = SubscriptionFeature.objects.filter(
            code=FEATURE_ANALYTICS_REGENERATION,
            is_active=True,
        ).first()

        if feature:
            CandidateFeatureUsage.increment_usage(candidate, feature)

    # ─── Vacancy & Template limit checks ──────────────────

    @staticmethod
    def _extract_vacancy_config(plan, features=None):
        """
        Extract vacancy-limit configuration from a pre-fetched features
        dict or from the PlanFeature table.

        Args:
            plan: SubscriptionPlan instance.
            features: Optional dict[code → PlanFeature] (from permission cache).

        Returns:
            dict with 'max_active_vacancies', 'max_expire_days', 'plan_name'.
        """
        pf = None
        if features is not None:
            pf = features.get(FEATURE_VACANCY_LIMIT)
        else:
            try:
                pf = PlanFeature.objects.get(
                    plan=plan,
                    feature__code=FEATURE_VACANCY_LIMIT,
                    is_enabled=True,
                )
            except PlanFeature.DoesNotExist:
                logger.warning(
                    "Plan '%s' is missing '%s' feature configuration. "
                    "Using defaults for vacancy limits.",
                    plan.name,
                    FEATURE_VACANCY_LIMIT,
                )

        fallback = DEFAULT_VACANCY_LIMITS.get(
            plan.slug, DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG]
        )

        if pf is not None:
            config = pf.configuration or {}
            return {
                "max_active_vacancies": config.get(
                    "max_active_vacancies", fallback["max_active_vacancies"]
                ),
                "max_expire_days": config.get(
                    "max_expire_days", fallback["max_expire_days"]
                ),
                "plan_name": plan.name,
            }

        return {**fallback, "plan_name": plan.name}

    @staticmethod
    def _extract_template_config(plan, features=None):
        """
        Extract template-limit configuration from a pre-fetched features
        dict or from the PlanFeature table.

        Args:
            plan: SubscriptionPlan instance.
            features: Optional dict[code → PlanFeature] (from permission cache).

        Returns:
            dict with 'max_reasons', 'plan_name'.
        """
        pf = None
        if features is not None:
            pf = features.get(FEATURE_TEMPLATE_LIMIT)
        else:
            try:
                pf = PlanFeature.objects.get(
                    plan=plan,
                    feature__code=FEATURE_TEMPLATE_LIMIT,
                    is_enabled=True,
                )
            except PlanFeature.DoesNotExist:
                logger.warning(
                    "Plan '%s' is missing '%s' feature configuration. "
                    "Using defaults for template limits.",
                    plan.name,
                    FEATURE_TEMPLATE_LIMIT,
                )

        fallback = DEFAULT_TEMPLATE_LIMITS.get(
            plan.slug, DEFAULT_TEMPLATE_LIMITS[COMPANY_FREE_PLAN_SLUG]
        )

        if pf is not None:
            config = pf.configuration or {}
            return {
                "max_reasons": config.get("max_reasons", fallback["max_reasons"]),
                "plan_name": plan.name,
            }

        return {**fallback, "plan_name": plan.name}

    @staticmethod
    def get_vacancy_limits(company, *, subscription=_NOT_PROVIDED, features=None) -> dict:
        """
        Get vacancy limits for a company based on its active subscription.

        When called from the permission layer the pre-fetched
        ``subscription`` and ``features`` should be passed to avoid
        redundant database queries.

        Args:
            company: The Company instance.
            subscription: Optional pre-fetched CompanySubscription.
                Use ``_NOT_PROVIDED`` sentinel (default) to auto-fetch.
            features: Optional dict[code → PlanFeature] from cache.

        Returns:
            dict with keys:
            - 'max_active_vacancies': int
            - 'max_expire_days': int
            - 'plan_name': str
        """
        if subscription is _NOT_PROVIDED:
            subscription = CompanySubscription.get_active(company)
        if subscription is None:
            defaults = DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG]
            return {**defaults, "plan_name": "Free (default)"}

        return SubscriptionService._extract_vacancy_config(
            subscription.plan, features
        )

    @staticmethod
    def check_vacancy_limit(company, *, subscription=_NOT_PROVIDED, features=None) -> dict:
        """
        Check if the company can create a new active vacancy.

        Args:
            company: The Company instance.
            subscription: Optional pre-fetched CompanySubscription.
            features: Optional dict[code → PlanFeature] from cache.

        Returns:
            dict with keys:
            - 'allowed': bool
            - 'max_active_vacancies': int
            - 'current_active': int
            - 'plan_name': str
            - 'error': str or None
        """
        from apps.vacancies.models import Vacancy

        limits = SubscriptionService.get_vacancy_limits(
            company, subscription=subscription, features=features
        )
        current_active = Vacancy.objects.filter(
            company=company, is_active=True
        ).count()

        if current_active >= limits["max_active_vacancies"]:
            return {
                "allowed": False,
                "max_active_vacancies": limits["max_active_vacancies"],
                "current_active": current_active,
                "plan_name": limits["plan_name"],
                "error": _(
                    "Active vacancy limit reached (%(max)d). "
                    "Upgrade your plan to create more vacancies."
                ) % {"max": limits["max_active_vacancies"]},
            }

        return {
            "allowed": True,
            "max_active_vacancies": limits["max_active_vacancies"],
            "current_active": current_active,
            "plan_name": limits["plan_name"],
            "error": None,
        }

    @staticmethod
    def check_vacancy_expire(
        company, expire_days: int, *, subscription=_NOT_PROVIDED, features=None
    ) -> dict:
        """
        Check if the requested expire value is within the plan's limits.

        Args:
            company: The Company instance.
            expire_days: The requested expiration in days.
            subscription: Optional pre-fetched CompanySubscription.
            features: Optional dict[code → PlanFeature] from cache.

        Returns:
            dict with keys:
            - 'allowed': bool
            - 'max_expire_days': int
            - 'plan_name': str
            - 'error': str or None
        """
        limits = SubscriptionService.get_vacancy_limits(
            company, subscription=subscription, features=features
        )
        max_expire = limits["max_expire_days"]

        if expire_days is not None and expire_days > max_expire:
            return {
                "allowed": False,
                "max_expire_days": max_expire,
                "plan_name": limits["plan_name"],
                "error": _(
                    "Vacancy expire cannot exceed %(max)d days "
                    "on the %(plan)s plan."
                ) % {"max": max_expire, "plan": limits["plan_name"]},
            }

        return {
            "allowed": True,
            "max_expire_days": max_expire,
            "plan_name": limits["plan_name"],
            "error": None,
        }

    @staticmethod
    def get_template_limits(company, *, subscription=_NOT_PROVIDED, features=None) -> dict:
        """
        Get status change template limits for a company based on its active subscription.

        Args:
            company: The Company instance.
            subscription: Optional pre-fetched CompanySubscription.
                Use ``_NOT_PROVIDED`` sentinel (default) to auto-fetch.
            features: Optional dict[code → PlanFeature] from cache.

        Returns:
            dict with keys:
            - 'max_reasons': int
            - 'plan_name': str
        """
        if subscription is _NOT_PROVIDED:
            subscription = CompanySubscription.get_active(company)
        if subscription is None:
            defaults = DEFAULT_TEMPLATE_LIMITS[COMPANY_FREE_PLAN_SLUG]
            return {**defaults, "plan_name": "Free (default)"}

        return SubscriptionService._extract_template_config(
            subscription.plan, features
        )

    # Backward compatibility aliases
    get_reason_limits = get_template_limits
    _extract_reason_config = _extract_template_config

    @staticmethod
    def check_template_limit(company, *, subscription=_NOT_PROVIDED, features=None) -> dict:
        """
        Check if the company can create a new status change template.
        Invitation templates are not counted towards the limit.

        Args:
            company: The Company instance.
            subscription: Optional pre-fetched CompanySubscription.
            features: Optional dict[code → PlanFeature] from cache.

        Returns:
            dict with keys:
            - 'allowed': bool
            - 'max_reasons': int
            - 'current_count': int
            - 'plan_name': str
            - 'error': str or None
        """
        from apps.hr_templates.models import Template

        limits = SubscriptionService.get_template_limits(
            company, subscription=subscription, features=features
        )
        # Only count STATUS_CHANGE templates towards the limit
        current_count = Template.objects.filter(
            company=company,
            template_type=Template.TemplateType.STATUS_CHANGE,
        ).count()

        if current_count >= limits["max_reasons"]:
            return {
                "allowed": False,
                "max_reasons": limits["max_reasons"],
                "current_count": current_count,
                "plan_name": limits["plan_name"],
                "error": _(
                    "Status change template limit reached (%(max)d). "
                    "Upgrade your plan to create more templates."
                ) % {"max": limits["max_reasons"]},
            }

        return {
            "allowed": True,
            "max_reasons": limits["max_reasons"],
            "current_count": current_count,
            "plan_name": limits["plan_name"],
            "error": None,
        }

    # Backward compatibility alias
    check_reason_limit = check_template_limit

    @staticmethod
    def get_seat_usage(subscription) -> dict:
        """
        Get current seat usage for a company subscription.

        Note: This always executes an aggregate query against
        ``subscription.seat_assignments``.  If you are serialising
        multiple subscriptions in a list and need seat_usage for each,
        consider prefetching ``seat_assignments`` on the queryset to
        avoid an extra query per object.

        Returns:
            dict with keys:
            - 'admin_seats_used': int
            - 'admin_seats_max': int
            - 'recruiter_seats_used': int
            - 'recruiter_seats_max': int
        """
        if subscription is None:
            return {
                "admin_seats_used": 0,
                "admin_seats_max": 0,
                "recruiter_seats_used": 0,
                "recruiter_seats_max": 0,
            }

        from django.db.models import Count, Q

        # Single aggregate query instead of two separate COUNTs.
        result = subscription.seat_assignments.filter(is_active=True).aggregate(
            admin_used=Count(
                "id", filter=Q(seat_type=SubscriptionSeatAssignment.SeatType.ADMIN)
            ),
            recruiter_used=Count(
                "id", filter=Q(seat_type=SubscriptionSeatAssignment.SeatType.RECRUITER)
            ),
        )

        return {
            "admin_seats_used": result["admin_used"],
            "admin_seats_max": subscription.plan.max_admins,
            "recruiter_seats_used": result["recruiter_used"],
            "recruiter_seats_max": subscription.plan.max_recruiters,
        }

    @staticmethod
    @transaction.atomic
    def assign_seat(subscription, recruiter, seat_type: str) -> tuple:
        """
        Assign a recruiter to a seat in the subscription.

        Runs inside its own ``@transaction.atomic`` block to guarantee
        that the limit check + row creation is consistent.  Callers
        (views) do **not** need an outer transaction unless they perform
        additional writes that must be atomic with the seat assignment.

        Uses ``select_for_update()`` on the subscription row to serialize
        concurrent seat assignments and prevent TOCTOU race conditions.

        Args:
            subscription: The CompanySubscription instance.
            recruiter: The Recruiter instance.
            seat_type: 'admin' or 'recruiter'.

        Returns:
            Tuple of (SubscriptionSeatAssignment | None, error_message | None)
        """
        # Lock the subscription row to serialize concurrent seat assignments
        subscription = CompanySubscription.objects.select_for_update().get(
            pk=subscription.pk
        )

        # Check if the recruiter already has an active seat
        existing = SubscriptionSeatAssignment.objects.filter(
            subscription=subscription,
            recruiter=recruiter,
            is_active=True,
        ).first()
        if existing:
            return None, _("This recruiter already has an active seat assignment.")

        # Check seat limits
        usage = SubscriptionService.get_seat_usage(subscription)
        if seat_type == SubscriptionSeatAssignment.SeatType.ADMIN:
            if usage["admin_seats_used"] >= usage["admin_seats_max"]:
                return None, _(
                    "Admin seat limit reached (%(max)d). "
                    "Upgrade your plan to add more admins."
                ) % {"max": usage["admin_seats_max"]}
        elif seat_type == SubscriptionSeatAssignment.SeatType.RECRUITER:
            if usage["recruiter_seats_used"] >= usage["recruiter_seats_max"]:
                return None, _(
                    "Recruiter seat limit reached (%(max)d). "
                    "Upgrade your plan to add more recruiters."
                ) % {"max": usage["recruiter_seats_max"]}
        else:
            return None, _("Invalid seat type: %(type)s") % {"type": seat_type}

        try:
            assignment = SubscriptionSeatAssignment.objects.create(
                subscription=subscription,
                recruiter=recruiter,
                seat_type=seat_type,
                is_active=True,
            )
        except IntegrityError:
            return None, _("This recruiter already has an active seat assignment.")

        logger.info(
            "Assigned %s seat to recruiter '%s' for subscription %s",
            seat_type,
            recruiter.email,
            subscription.id,
        )
        return assignment, None

    @staticmethod
    @transaction.atomic
    def revoke_seat(subscription, recruiter) -> tuple:
        """
        Revoke a recruiter's seat assignment.

        Runs inside ``@transaction.atomic`` similarly to :py:meth:`assign_seat`.

        Args:
            subscription: The CompanySubscription instance.
            recruiter: The Recruiter instance.

        Returns:
            Tuple of (success: bool, error_message | None)
        """
        assignment = SubscriptionSeatAssignment.objects.filter(
            subscription=subscription,
            recruiter=recruiter,
            is_active=True,
        ).first()

        if assignment is None:
            return False, _("This recruiter does not have an active seat assignment.")

        assignment.is_active = False
        assignment.save(update_fields=["is_active", "updated_at"])

        logger.info(
            "Revoked seat for recruiter '%s' from subscription %s",
            recruiter.email,
            subscription.id,
        )
        return True, None
