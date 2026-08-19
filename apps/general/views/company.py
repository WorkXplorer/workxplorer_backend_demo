
import logging
from rest_framework import status
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from core.responses import APIResponse
from apps.authentication.models import Company
from apps.authentication.serializers import CompanySerializer
from apps.general.services.company_email_service import send_company_confirmation_emails
from utils import IsAdminRecruiter
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class CompanyConfirmAPIView(APIView):
    """
    Accepts POST with:
      {
        "company_ids": ["id1", "id2", ...],
        "is_active": true|false
      }

    Delegates email processing to send_company_confirmation_emails()
    so that both the view and background tasks use the same logic.
    """

    permission_classes = [IsAuthenticated, IsAdminRecruiter]

    def get(self, request, *args, **kwargs):
        return APIResponse.error(
            message='Method "GET" not allowed.',
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def post(self, request, *args, **kwargs):
        try:
            company_ids = request.data.get("company_ids")
            if company_ids is None or not isinstance(company_ids, list):
                return APIResponse.bad_request(
                    message=_("company_ids must be a list of company id strings.")
                )

            if "is_active" not in request.data:
                return APIResponse.bad_request(
                    message=_("is_active field is required and must be boolean.")
                )

            is_active_raw = request.data["is_active"]
            if isinstance(is_active_raw, bool):
                is_active = is_active_raw
            elif isinstance(is_active_raw, str):
                val = is_active_raw.strip().lower()
                if val in ("true", "1", "yes"):
                    is_active = True
                elif val in ("false", "0", "no"):
                    is_active = False
                else:
                    return APIResponse.bad_request(
                        message=_("is_active must be a boolean.")
                    )
            elif isinstance(is_active_raw, (int, float)):
                is_active = bool(is_active_raw)
            else:
                return APIResponse.bad_request(
                    message=_("is_active must be a boolean.")
                )

            result = send_company_confirmation_emails(
                company_ids=company_ids,
                is_active=is_active,
                request=request,
            )

            return APIResponse.success(
                data=result,
                message=_("Company confirmation emails processed"),
            )

        except Exception as exc:
            logger.exception("Unhandled error in CompanyConfirmAPIView.post: %s", exc)
            return APIResponse.server_error(
                message=_("An internal error occurred while processing the request.")
            )


class InActiveCompanyAPIView(generics.ListAPIView):
    queryset = Company.objects.filter(is_active=False)
    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated, IsAdminRecruiter]


inactive_company_view = InActiveCompanyAPIView.as_view()
company_confirm_view = CompanyConfirmAPIView.as_view()
