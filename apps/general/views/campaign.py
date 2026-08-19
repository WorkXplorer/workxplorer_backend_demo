import logging

from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.general.serializers import ManualEmailCampaignSerializer
from apps.general.services.campaign_email_service import ManualEmailCampaignService
from core.responses import APIResponse

logger = logging.getLogger(__name__)


class ManualEmailCampaignAPIView(APIView):
    """
    Manually send candidate/recruiter marketing emails from an EmailTemplate.
    """

    permission_classes = [IsAdminUser]

    def post(self, request, *args, **kwargs):
        serializer = ManualEmailCampaignSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return APIResponse.validation_error(
                message=_("Input validation failed"),
                field_errors=serializer.errors,
            )

        try:
            result = ManualEmailCampaignService(request=request).send(
                serializer.validated_data
            )
        except KeyError as exc:
            logger.exception("Manual email campaign missing required field: %s", exc)
            return APIResponse.server_error(
                message=_("Missing required configuration: %(field)s")
                % {"field": str(exc)}
            )
        except ConnectionError as exc:
            logger.exception("Manual email campaign connection error: %s", exc)
            return APIResponse.server_error(
                message=_("Failed to connect to email service. Please try again later.")
            )
        except Exception as exc:
            logger.exception("Manual email campaign failed: %s", exc)
            return APIResponse.server_error(
                message=_("Failed to process manual email campaign. Please try again later.")
            )

        return APIResponse.success(
            data=result,
            message=_("Manual email campaign processed."),
            status_code=status.HTTP_200_OK,
        )


manual_email_campaign_view = ManualEmailCampaignAPIView.as_view()