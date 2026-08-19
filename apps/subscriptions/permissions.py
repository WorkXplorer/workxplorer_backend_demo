"""
Subscription-based permissions.

These permission classes can be added to any view to enforce
subscription feature access control.

All permission classes use **request-level caching** to avoid duplicate
database queries when multiple subscription permissions are stacked on
the same view.  Cached attributes on the request object:

    _subscription_company   - Company resolved from the recruiter
    _subscription_active    - The active CompanySubscription (or None)
    _subscription_features  - dict[code, PlanFeature] of enabled features

Usage:
    from apps.subscriptions.permissions import HasSubscriptionFeature

    class MyView(APIView):
        permission_classes = [IsRecruiterPermission, HasSubscriptionFeature]
        required_feature = 'headhunting_access'
"""
import logging
from rest_framework.permissions import BasePermission
from django.utils.translation import gettext_lazy as _

from apps.subscriptions.services import SubscriptionService

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────
# Request-level caching helpers
# ──────────────────────────────────────────────────────

_CACHE_COMPANY = "_subscription_company"
_CACHE_SUBSCRIPTION = "_subscription_active"
_CACHE_FEATURES = "_subscription_features"
_CACHE_SENTINEL = "_subscription_resolved"
_CACHE_RECRUITER = "_recruiter_cache"


def _cache_target(request):
    """Return the object on which to store per-request caches.

    DRF's ``BrowsableAPIRenderer`` calls ``clone_request()`` to create
    temporary DRF Request objects for each form-method permission check.
    Custom attributes set on the DRF Request are **lost** on the clone.

    The underlying Django ``HttpRequest`` (``request._request``) is
    shared across all clones, so caches stored there survive the
    renderer's permission re-checks and prevent duplicate DB queries.
    """
    return getattr(request, "_request", request)


def _resolve_subscription_context(request):
    """
    Resolve and cache company → subscription → features on the request.

    This is called once per request; subsequent calls are no-ops.
    The function reuses ``_recruiter_cache`` from
    :class:`~utils.view_mixins.RecruiterMixin` when available,
    preventing a redundant Recruiter query.

    All cache attributes are stored on the underlying Django
    ``HttpRequest`` so they survive DRF request cloning.
    """
    target = _cache_target(request)

    if getattr(target, _CACHE_SENTINEL, False):
        return

    from apps.authentication.models import Recruiter
    from apps.subscriptions.models import CompanySubscription, PlanFeature

    company = None
    subscription = None
    features = {}

    user = request.user
    if user.is_authenticated and getattr(user, "is_recruiter", False):
        # 1) Try RecruiterMixin cache first
        recruiter = getattr(target, _CACHE_RECRUITER, None)
        if recruiter is not None:
            company = recruiter.company
        else:
            # Inline company from user (multi-table inheritance)
            company = getattr(user, "company", None)
            if company is None:
                try:
                    recruiter = Recruiter.objects.select_related("company").get(
                        pk=user.pk
                    )
                    company = recruiter.company
                    # Store so RecruiterMixin and views can reuse it
                    setattr(target, _CACHE_RECRUITER, recruiter)
                except Recruiter.DoesNotExist:
                    logger.warning(f"Authenticated recruiter user ID {user.pk} has no Recruiter profile")
            else:
                # User is a Recruiter instance with company already hydrated.
                # Cache it so RecruiterMixin.get_recruiter() doesn't re-query.
                setattr(target, _CACHE_RECRUITER, user)

        # 2) Get active subscription (single query with select_related)
        if company is not None:
            subscription = CompanySubscription.get_active(company)

        # 3) Pre-fetch all enabled features for the plan (single query)
        if subscription is not None:
            plan_features = PlanFeature.objects.filter(
                plan=subscription.plan,
                is_enabled=True,
            ).select_related("feature")
            features = {pf.feature.code: pf for pf in plan_features}

    setattr(target, _CACHE_COMPANY, company)
    setattr(target, _CACHE_SUBSCRIPTION, subscription)
    setattr(target, _CACHE_FEATURES, features)
    setattr(target, _CACHE_SENTINEL, True)


def get_cached_company(request):
    """Return the cached company for this request (may be None)."""
    _resolve_subscription_context(request)
    return getattr(_cache_target(request), _CACHE_COMPANY, None)


def get_cached_subscription(request):
    """Return the cached active CompanySubscription (may be None)."""
    _resolve_subscription_context(request)
    return getattr(_cache_target(request), _CACHE_SUBSCRIPTION, None)


def get_cached_features(request):
    """Return dict[code → PlanFeature] of enabled features."""
    _resolve_subscription_context(request)
    return getattr(_cache_target(request), _CACHE_FEATURES, {})


def get_cached_recruiter(request):
    """Return the cached Recruiter instance for this request (may be None)."""
    return getattr(_cache_target(request), _CACHE_RECRUITER, None)


def set_cached_recruiter(request, recruiter):
    """Store a Recruiter instance in the per-request cache."""
    setattr(_cache_target(request), _CACHE_RECRUITER, recruiter)


# ──────────────────────────────────────────────────────
# Permission classes
# ──────────────────────────────────────────────────────

class HasSubscriptionFeature(BasePermission):
    """
    Permission class that checks if the user's subscription
    includes a specific feature.

    The feature code must be set as `required_feature` on the view.

    For recruiters: checks the company's active subscription.
    For candidates: checks the candidate's active subscription.

    Example:
        class HeadhuntingView(APIView):
            permission_classes = [IsRecruiterPermission, HasSubscriptionFeature]
            required_feature = 'headhunting_access'
    """

    message = _("Your current subscription plan does not include this feature.")

    def has_permission(self, request, view):
        feature_code = getattr(view, "required_feature", None)
        if feature_code is None:
            return True

        user = request.user
        if not user.is_authenticated:
            return False

        if getattr(user, "is_recruiter", False):
            features = get_cached_features(request)
            return feature_code in features

        if getattr(user, "is_candidate", False):
            return SubscriptionService.candidate_has_feature(user, feature_code)

        return False


class HasHeadhuntingAccess(HasSubscriptionFeature):
    """
    Shortcut permission for headhunting access.

    Checks if the recruiter's company subscription includes
    the 'headhunting_access' feature.

    Usage:
        class HeadhuntingView(APIView):
            permission_classes = [IsRecruiterPermission, HasHeadhuntingAccess]
    """

    message = _(
        "Your subscription plan does not include access to unresponded candidates. "
        "Upgrade to Basic or Pro to send offers and invitations."
    )

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False

        if getattr(user, "is_recruiter", False):
            features = get_cached_features(request)
            return "headhunting_access" in features

        return False


class CanCreateVacancy(BasePermission):
    """
    Checks that the recruiter's company has not exceeded the maximum
    number of active vacancies allowed by the current subscription plan.

    Attach to CreateVacancyView.

    If the request user is not a recruiter or has no company, this
    permission passes — the view's own logic produces appropriate errors.
    """

    def has_permission(self, request, view):
        if request.method not in ("POST",):
            return True

        company = get_cached_company(request)
        if company is None:
            # ponytail: fail closed — non-recruiters shouldn't reach here,
            # but if they do, deny instead of silently passing.
            return False

        result = SubscriptionService.check_vacancy_limit(
            company,
            subscription=get_cached_subscription(request),
            features=get_cached_features(request),
        )
        if not result["allowed"]:
            self.message = _(
                "Active vacancy limit reached (%(max)d). "
                "Your current plan is '%(plan)s'. "
                "Upgrade your subscription to create more vacancies."
            ) % {"max": result["max_active_vacancies"], "plan": result["plan_name"]}
            return False
        return True


class CanSetVacancyExpire(BasePermission):
    """
    Checks that the requested vacancy `expire` value does not exceed
    the maximum allowed by the company's subscription plan.

    Attach to CreateVacancyView and UpdateVacancyView.

    If the request user is not a recruiter or has no company, this
    permission passes — the view's own logic produces appropriate errors.
    """

    def has_permission(self, request, view):
        if request.method not in ("POST", "PUT", "PATCH"):
            return True

        expire_days = request.data.get("expire")
        if expire_days is None:
            return True

        try:
            expire_days = int(expire_days)
        except (ValueError, TypeError):
            return False

        company = get_cached_company(request)
        if company is None:
            # ponytail: fail closed
            return False

        result = SubscriptionService.check_vacancy_expire(
            company,
            expire_days,
            subscription=get_cached_subscription(request),
            features=get_cached_features(request),
        )
        if not result["allowed"]:
            self.message = _(
                "Vacancy expiration cannot exceed %(max)d days "
                "on the '%(plan)s' plan. "
                "Upgrade your subscription for a longer expiration period."
            ) % {"max": result["max_expire_days"], "plan": result["plan_name"]}
            return False
        return True


class CanCreateTemplate(BasePermission):
    """
    Checks that the recruiter's company has not exceeded the maximum
    number of status change templates allowed by the current subscription plan.
    Invitation templates are not counted towards the limit.

    Attach to TemplateListCreateView.

    If the request user is not a recruiter or has no company, this
    permission passes — earlier permissions (IsRecruiterPermission)
    handle those checks.
    """

    def has_permission(self, request, view):
        if request.method not in ("POST",):
            return True

        company = get_cached_company(request)
        if company is None:
            # ponytail: fail closed
            return False

        result = SubscriptionService.check_template_limit(
            company,
            subscription=get_cached_subscription(request),
            features=get_cached_features(request),
        )
        if not result["allowed"]:
            self.message = _(
                "Status change template limit reached (%(max)d). "
                "Your current plan is '%(plan)s'. "
                "Upgrade your subscription to create more templates."
            ) % {"max": result["max_reasons"], "plan": result["plan_name"]}
            return False
        return True


# Backward compatibility aliases
CanCreateReason = CanCreateTemplate

