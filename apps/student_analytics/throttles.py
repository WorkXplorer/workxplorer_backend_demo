from rest_framework.throttling import BaseThrottle

from apps.authentication.models.candidate import Candidate


class AnalyticsRegenerationThrottle(BaseThrottle):
    def allow_request(self, request, view):
        if request.method not in ("POST", "PUT", "PATCH"):
            return True

        user = request.user
        if not user.is_authenticated:
            return False
        if not getattr(user, "is_candidate", False):
            return True

        # request.user is a CustomUser instance; we need the real Candidate
        # instance so that FK lookups (candidate=…) work correctly.
        candidate = Candidate.objects.only("pk").get(pk=user.pk)

        from apps.subscriptions.services import SubscriptionService

        result = SubscriptionService.check_analytics_regeneration_limit(candidate)
        if not result["allowed"]:
            return False

        SubscriptionService.record_analytics_regeneration(candidate)
        return True

    def wait(self):
        return 86400
