from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
import os

from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from apps.authentication.models import Recruiter
from apps.subscriptions.models import CompanySubscription, PlanFeature
from core.responses import APIResponse

import logging

logger = logging.getLogger(__name__)


class ValidateTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        logger.info("ValidateTokenView called")
        logger.debug(f"Request data: {request.data}")

        token = request.data.get("token")
        if not token:
            return APIResponse.bad_request(
                message=_("Token is required"),
            )

        try:
            payload = UntypedToken(token).payload
        except (TokenError, InvalidToken) as e:
            logger.error(f"Token validation failed: {str(e)}")
            return APIResponse.unauthorized(
                message=_("Invalid or expired token"),
            )

        token_env = payload.get('env')
        current_env = os.environ.get('DJANGO_ENVIRONMENT', 'production')
        if token_env and token_env != current_env:
            logger.warning(
                f"[validate_token] Cross-environment token rejected: "
                f"token.env={token_env!r}, server.env={current_env!r}"
            )
            return APIResponse.unauthorized(
                message=_("Token issued for a different environment - please log in again"),
            )

        user_id = payload.get("user_id")
        if not user_id:
            return APIResponse.bad_request(
                message=_("Invalid token payload"),
            )

        logger.info(f"[validate_token] Looking up user_id={user_id}")

        # Step 1: verify the base user account exists
        User = get_user_model()
        try:
            base_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            logger.warning(
                f"[validate_token] No CustomUser row found for user_id={user_id}. "
                f"This may indicate a JWT from a different environment."
            )
            return APIResponse.not_found(
                message=_("User not found"),
            )
        except Exception as e:
            logger.error(f"[validate_token] Error fetching user {user_id}: {type(e).__name__}: {e}")
            return APIResponse.error(
                message=_("Internal error"),
                code="SERVER_ERROR",
                status_code=500,
            )

        # Step 2: check recruiter flag
        if not base_user.is_recruiter:
            logger.warning(f"[validate_token] user_id={user_id} exists but is_recruiter=False")
            return APIResponse.forbidden(
                message=_("User is not a recruiter"),
            )

        # Step 3: get Recruiter MTI row for company info
        try:
            user = Recruiter.objects.select_related("company").get(id=user_id)
        except Recruiter.DoesNotExist:
            # is_recruiter=True on CustomUser but no row in authentication_recruiter.
            # Likely the account was seeded directly via CustomUser instead of Recruiter.
            logger.error(
                f"[validate_token] MTI integrity failure: user_id={user_id} "
                f"has is_recruiter=True but no row in authentication_recruiter table."
            )
            return APIResponse.error(
                message=_("Recruiter profile incomplete — contact support"),
                code="RECRUITER_PROFILE_MISSING",
                status_code=500,
            )
        except Exception as e:
            logger.error(f"[validate_token] Error fetching recruiter {user_id}: {type(e).__name__}: {e}")
            return APIResponse.error(
                message=_("Internal error"),
                code="SERVER_ERROR",
                status_code=500,
            )

        # Get subscription features for the user's company
        features = []
        if user.company:
            subscription = CompanySubscription.get_active(user.company)
            if subscription:
                plan_features = PlanFeature.objects.filter(
                    plan=subscription.plan,
                    is_enabled=True,
                ).select_related("feature")
                features = [
                    {
                        "code": pf.feature.code,
                        "name": pf.feature.name,
                        "configuration": pf.configuration,
                    }
                    for pf in plan_features
                ]

        return APIResponse.success(
            data={
                "user": {
                    "uuid": str(user.id),
                    "company_id": user.company_id,
                    "company_is_active": (
                        user.company.is_active if user.company else None
                    ),
                },
                "subscription_features": features,
            },
            message=_("Token validated successfully"),
        )


validate_token = ValidateTokenView.as_view()
