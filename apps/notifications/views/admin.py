# This section is for admin users to send notifications to all registered devices.
import uuid
import logging

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from core.responses import APIResponse

from django.db import transaction
from django.db.models import Prefetch
from django.contrib.auth import get_user_model

from apps.notifications.models import Notification, NotificationRecipient
from apps.notifications.services import NotificationService
from apps.applications.models.applications import JobApplication
from apps.authentication.models.recruiter import Recruiter
from fcm_django.models import FCMDevice
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@extend_schema(
    description=(
            "Send a push notification to all registered devices. "
            "Only accessible by admin users. "
            "The `data` field is optional and can contain additional custom key-value pairs."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "example": "Important Update"},
                "message": {
                    "type": "string",
                    "example": "Please check the latest updates in your app.",
                },
                "data": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "example": {"key1": "value1", "key2": "value2"},
                },
                "sent_to_all": {"type": "boolean", "example": True},
            },
            "required": ["title", "message", "sent_to_all"],
        }
    },
    responses={
        200: OpenApiResponse(
            description="Notification sent successfully to all devices",
            examples=[
                OpenApiExample(
                    "Success Example",
                    value={
                        "message": "Notification dispatched to devices.",
                        "sent_count": 120,
                        "success_count": 118,
                        "failure_count": 2,
                        "notification_id": 45,
                    },
                )
            ],
        ),
        400: OpenApiResponse(
            description="Missing required fields in request body",
            examples=[
                OpenApiExample(
                    "Bad Request Example",
                    value={"error": "Title, message, and sent_to_all are required."},
                )
            ],
        ),
        404: OpenApiResponse(
            description="No devices available to send notifications",
            examples=[
                OpenApiExample(
                    "No Devices Example",
                    value={"error": "No active devices found."},
                )
            ],
        ),
    },
)
class SendNotificationAPIView(APIView):
    """
    API endpoint for admin users to send push notifications to all registered devices.
    Only accessible by admin users.
    Example request payload:
    {
        "title": "Important Update",
        "message": "Please check the latest updates in your app.",
        "data": {
            "key1": "value1",
            "key2": "value2"
        },
        "sent_to_all": true
    }
    The "data" field is optional and can include any additional information to send with the notification.
    """

    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request, *args, **kwargs):
        """
        Send a push notification to all registered devices.
        Expected payload:
        {
            "title": "Important Update",
            "message": "Please check the latest updates in your app.",
            "data": {
                "key1": "value1",
                "key2": "value2"
            },
            "sent_to_all": true
        }
        """
        data = request.data.get("data", {})
        title = request.data.get("title")
        message = request.data.get("message")
        sent_to_all = request.data.get("sent_to_all")

        if not title or not message or not sent_to_all:
            return APIResponse.bad_request(
                message=_("Title, message, and sent_to_all are required.")
            )

        # Create the notification record
        notification = Notification.objects.create(
            title=title,
            message=message,
            sent_to_all=True,  # Always true for this endpoint, because admin is sending to all
        )

        # Fetch all active devices
        devices = NotificationService.get_active_devices()
        if not devices.exists():
            return APIResponse.not_found(message=_("No active devices found."))

        # Prepare notification data
        notification_data = {
            "notification_id": str(notification.id),
            "timestamp": str(notification.created_at),
        }
        if data:
            notification_data.update(data)

        # Convert all values to strings for FCM
        notification_data_str = {k: str(v) for k, v in notification_data.items()}

        # Send the notification to all devices
        result = NotificationService.send_to_devices(
            list(devices), title, message, notification_data_str
        )

        # Update notification statistics
        NotificationService.update_notification_stats(
            notification, result["success_count"], result["failure_count"]
        )

        return APIResponse.success(
            data={
                "sent_count": notification.sent_count,
                "success_count": notification.success_count,
                "failure_count": notification.failure_count,
                "notification_id": notification.id,
            },
            message=_("Notification dispatched to devices."),
        )


class SendNotificationToMultipleUsersAPIView(APIView):
    """
    API endpoint for admin users to send push notifications to multiple specific users.
    Only accessible by admin users.

    Example request payload:
    {
        "user_ids": [
            "123e4567-e89b-12d3-a456-426614174000",
            "987fcdeb-51d2-43a8-b123-123456789abc"
        ],
        "title": "Group Message",
        "message": "Important announcement for selected users",
        "notification_type": "platform_announcement",
        "data": {
            "announcement_id": "789"
        }
    }
    """

    permission_classes = (IsAuthenticated, IsAdminUser)

    @extend_schema(
        summary="Send notifications to multiple users",
        description="Admin users can send push notifications to multiple specific users.",
        request={
            "application/json": {
                "type": "object",
                "required": ["user_ids", "title", "message"],
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "description": "List of user UUIDs",
                    },
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                    "notification_type": {
                        "type": "string",
                        "enum": [
                            choice[0]
                            for choice in Notification.NotificationType.choices
                        ],
                    },
                    "data": {"type": "object"},
                },
            }
        },
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "notification_id": {"type": "integer"},
                        "total_users": {"type": "integer"},
                        "total_devices": {"type": "integer"},
                        "push_notifications_sent": {"type": "integer"},
                        "not_found_user_ids": {
                            "type": "array",
                            "items": {"type": "string", "format": "uuid"},
                        },
                        "user_results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "user_id": {"type": "string", "format": "uuid"},
                                    "email": {"type": "string"},
                                    "devices_count": {"type": "integer"},
                                    "success_count": {"type": "integer"},
                                    "success": {"type": "boolean"},
                                },
                            },
                        },
                    },
                },
                description="Notifications sent successfully",
            ),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Users Not Found"),
            500: OpenApiResponse(description="Internal Server Error"),
        },
    )
    def post(self, request, *args, **kwargs):
        """
        Send push notifications to multiple specific users.
        """
        # Extract data from request
        user_ids = request.data.get("user_ids", [])
        title = request.data.get("title")
        message_text = request.data.get("message")
        notification_type = request.data.get(
            "notification_type", Notification.NotificationType.PLATFORM_ANNOUNCEMENT
        )
        data = request.data.get("data", {})

        # Validate required fields
        if not all([user_ids, title, message_text]):
            return APIResponse.bad_request(
                message=_("user_ids (array), title, and message are required.")
            )

        # Validate user_ids is a list
        if not isinstance(user_ids, list) or len(user_ids) == 0:
            return APIResponse.bad_request(
                message=_("user_ids must be a non-empty array of UUIDs.")
            )

        # Validate UUID formats
        for user_id in user_ids:
            try:
                uuid.UUID(str(user_id))
            except ValueError:
                return APIResponse.bad_request(
                    message=f"Invalid user_id format: {user_id}. Must be a valid UUID."
                )

        # Validate notification type
        valid_types = [choice[0] for choice in Notification.NotificationType.choices]
        if notification_type not in valid_types:
            return APIResponse.bad_request(
                message=f"Invalid notification_type. Must be one of: {valid_types}"
            )

        try:
            with transaction.atomic():
                # Create the notification record
                notification = Notification.objects.create(
                    title=title,
                    message=message_text,
                    notification_type=notification_type,
                    data=data,
                    sent_to_all=False,
                    created_by=request.user,
                )

                # Get existing users
                users = User.objects.filter(id__in=user_ids, is_active=True)
                found_user_ids = set(str(user.id) for user in users)
                not_found_user_ids = set(user_ids) - found_user_ids

                if not users.exists():
                    return APIResponse.not_found(
                        message=_("No valid active users found.")
                    )

                # Create notification recipients
                recipients = []
                for user in users:
                    recipients.append(
                        NotificationRecipient(notification=notification, user=user)
                    )
                NotificationRecipient.objects.bulk_create(recipients)

                # Send push notifications
                total_success = 0
                total_devices = 0
                user_results = []

                for user in users:
                    push_result = self._send_push_notification_to_user(
                        user, notification, title, message_text, data
                    )
                    total_success += push_result["success_count"]
                    total_devices += push_result["devices_count"]

                    user_results.append(
                        {
                            "user_id": str(user.id),
                            "email": user.email,
                            "devices_count": push_result["devices_count"],
                            "success_count": push_result["success_count"],
                            "success": push_result["success"],
                        }
                    )

                    # Clear user's notification cache
                    self._clear_user_notification_cache(user.id)

                # Update notification statistics
                notification.sent_count = len(users)
                notification.success_count = len(
                    users
                )  # All users received the notification record
                notification.failure_count = 0
                notification.save()

                return APIResponse.success(
                    data={
                        "notification_id": notification.id,
                        "total_users": len(users),
                        "total_devices": total_devices,
                        "push_notifications_sent": total_success,
                        "not_found_user_ids": list(not_found_user_ids),
                        "user_results": user_results,
                    },
                    message=_("Notifications sent successfully."),
                )

        except Exception as e:
            logger.error(f"Error sending notifications to multiple users: {str(e)}")
            return APIResponse.server_error(
                message=_("Failed to send notifications. Please try again.")
            )

    def _send_push_notification_to_user(
            self, user, notification, title, message_text, data
    ):
        """Send push notification to a single user's devices"""
        return NotificationService.send_to_user(
            user, notification, title, message_text, data
        )

    def _clear_user_notification_cache(self, user_id):
        """Clear user's notification related cache"""
        NotificationService.clear_user_notification_cache(str(user_id))


class NewJobApplicationNotificationView(APIView):
    """
    API endpoint to send notifications to recruiters when a new job application is submitted.
    Sends both database notifications and FCM push notifications.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Send new job application notification",
        description=(
                "This endpoint sends database and push notifications "
                "to all recruiters of the company when a candidate applies for a job."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "job_application_id": {
                        "type": "string",
                        "format": "uuid",
                        "example": "550e8400-e29b-41d4-a716-446655440000",
                    }
                },
                "required": ["job_application_id"],
            }
        },
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "example": "Notification sent successfully to recruiters",
                        },
                        "job_application_id": {"type": "string", "format": "uuid"},
                        "recruiters_notified": {"type": "integer", "example": 5},
                        "push_notifications_sent": {"type": "integer", "example": 5},
                        "notification_id": {"type": "string", "example": "123"},
                    },
                },
                description="Notification sent successfully",
            ),
            400: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "error": {
                            "type": "string",
                            "example": "job_application_id is required",
                        }
                    },
                },
                description="Bad request (missing or invalid job_application_id)",
            ),
            500: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "error": {"type": "string", "example": "Internal server error"}
                    },
                },
                description="Internal server error",
            ),
        },
        examples=[
            OpenApiExample(
                "Valid request example",
                value={"job_application_id": "550e8400-e29b-41d4-a716-446655440000"},
                request_only=True,
            ),
            OpenApiExample(
                "Successful response example",
                value={
                    "message": "Notification sent successfully to recruiters",
                    "job_application_id": "550e8400-e29b-41d4-a716-446655440000",
                    "recruiters_notified": 5,
                    "push_notifications_sent": 5,
                    "notification_id": "123",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        """
        Send notification to all recruiters of the company when a candidate applies for a job.

        Expected payload:
        {
            "job_application_id": "uuid-string"
        }
        """
        try:
            job_application_id = request.data.get("job_application_id")

            # Validate required fields
            if not job_application_id:
                return APIResponse.bad_request(
                    message=_("job_application_id is required")
                )

            # Validate UUID format
            try:
                uuid.UUID(str(job_application_id))
            except ValueError:
                return APIResponse.bad_request(
                    message=_("Invalid job_application_id format. Must be a valid UUID.")
                )

            # Get authenticated user (candidate)
            candidate = request.user

            # Send notification to recruiters
            result = self.notify_recruiters_new_application(
                job_application_id=job_application_id, candidate=candidate
            )

            if result["success"]:
                return APIResponse.success(
                    data={
                        "job_application_id": job_application_id,
                        "recruiters_notified": result["recruiters_count"],
                        "push_notifications_sent": result["push_success_count"],
                        "notification_id": str(result["notification_id"]),
                    },
                    message=_("Notification sent successfully to recruiters"),
                )
            else:
                return APIResponse.server_error(
                    message=result.get("error", "Failed to send notification")
                )

        except Exception as e:
            logger.error(f"Error in NewJobApplicationNotificationView: {str(e)}")
            return APIResponse.server_error(
                message=_("Internal server error")
            )

    def notify_recruiters_new_application(
            self, job_application_id: str, candidate
    ) -> dict:
        """
        Send notification to all recruiters of the company for new job application.

        Args:
            job_application_id (str): Job application ID
            candidate: Authenticated user (candidate)

        Returns:
            dict: Result with success status and details
        """

        try:
            job_application = get_object_or_404(
                JobApplication.objects.select_related(
                    "vacancy__company", "vacancy__created_by"
                ).only(
                    "id",
                    "vacancy__id",
                    "vacancy__title",
                    "vacancy__is_active",
                    "vacancy__company__id",
                    "vacancy__company__name",
                    "vacancy__created_by__id",
                ),
                id=job_application_id,
                candidate=candidate,
            )

            vacancy = job_application.vacancy

            # Check if vacancy is still active
            if not vacancy.is_active:
                logger.warning(f"Vacancy {vacancy.id} is not active")
                return {
                    "success": False,
                    "error": "Vacancy is not active",
                    "recruiters_count": 0,
                    "push_success_count": 0,
                }

            # OPTIMIZATION 2: Fetch recruiters and their active devices in one query
            # Prefetch only active devices to avoid loading inactive ones
            recruiters = (
                Recruiter.objects.filter(company=vacancy.company, is_active=True)
                .prefetch_related(
                    Prefetch(
                        "fcmdevice_set",
                        queryset=FCMDevice.objects.filter(active=True),
                    )
                )
                .only(
                    "id",
                    "email",
                    "is_active",
                    "company__id",
                )
            )

            if not recruiters.exists():
                logger.warning(
                    f"No active recruiters found for company {vacancy.company.name}"
                )
                return {
                    "success": False,
                    "error": "No active recruiters found for company",
                    "recruiters_count": 0,
                    "push_success_count": 0,
                }

            with transaction.atomic():
                # Prepare notification data
                candidate_name = candidate.email

                notification_data = {
                    "job_application_id": str(job_application_id),
                    "vacancy_id": str(vacancy.id),
                    "vacancy_title": vacancy.title,
                    "company_name": vacancy.company.name,
                    "candidate_name": candidate_name,
                    "candidate_email": candidate.email,
                    "redirect_url": f"/recruiter/applications/{job_application_id}",
                }

                # Create notification object
                notification = Notification.objects.create(
                    title=f"New Application: {vacancy.title}",
                    message=f"{candidate_name} has applied for the position '{vacancy.title}'. "
                            f"Click to review the application and candidate profile.",
                    notification_type=Notification.NotificationType.APPLICATION_OFFERED,
                    data=notification_data,
                    sent_to_all=False,
                    created_by=vacancy.created_by,
                )

                recipients_to_create = [
                    NotificationRecipient(notification=notification, user=recruiter)
                    for recruiter in recruiters
                ]

                NotificationRecipient.objects.bulk_create(recipients_to_create)

                total_push_success = self._send_bulk_push_notifications(
                    recruiters, notification, notification_data
                )

                user_ids = [recruiter.id for recruiter in recruiters]
                self._clear_multiple_user_caches(user_ids)

                # Update notification statistics
                notification.sent_count = len(recipients_to_create)
                notification.success_count = len(recipients_to_create)
                notification.failure_count = 0
                notification.save(
                    update_fields=["sent_count", "success_count", "failure_count"]
                )

            logger.info(
                f"Successfully sent notification to {len(recipients_to_create)} recruiters "
                f"for job application {job_application_id}. "
                f"Push notifications sent to {total_push_success} devices."
            )

            return {
                "success": True,
                "recruiters_count": len(recipients_to_create),
                "push_success_count": total_push_success,
                "notification_id": notification.id,
            }

        except JobApplication.DoesNotExist:
            logger.error(
                f"Job application with ID {job_application_id} not found or doesn't belong to user"
            )
            return {
                "success": False,
                "error": "Job application not found or access denied",
                "recruiters_count": 0,
                "push_success_count": 0,
            }
        except Exception as e:
            logger.error(
                f"Error sending notification for job application {job_application_id}: {str(e)}"
            )
            return {
                "success": False,
                "error": f"Failed to send notification: {str(e)}",
                "recruiters_count": 0,
                "push_success_count": 0,
            }

    def _send_bulk_push_notifications(
            self, recruiters, notification, notification_data
    ):
        """
        Send FCM push notifications to multiple recruiters efficiently

        Args:
            recruiters: QuerySet of recruiters (already prefetched with devices)
            notification: Notification object
            notification_data: Additional data to send with notification

        Returns:
            int: Total number of successful push notifications sent
        """
        try:
            # Prepare FCM message data once
            fcm_data = {
                "notification_id": str(notification.id),
                "notification_type": notification.notification_type,
                "job_application_id": notification_data["job_application_id"],
                "vacancy_id": notification_data["vacancy_id"],
                "vacancy_title": notification_data["vacancy_title"],
                "candidate_name": notification_data["candidate_name"],
                "redirect_url": notification_data["redirect_url"],
                "timestamp": str(notification.created_at),
            }

            # Convert all values to strings for FCM
            fcm_data_str = {k: str(v) for k, v in fcm_data.items()}

            # Collect all active devices from prefetched recruiter relations.
            all_devices = []

            for recruiter in recruiters:
                all_devices.extend(recruiter.fcmdevice_set.all())

            if not all_devices:
                logger.warning("No active devices found for any recruiters")
                return 0

            result = NotificationService.send_to_devices(
                all_devices,
                notification.title,
                notification.message,
                fcm_data_str,
            )
            logger.info(
                "Recruiter push notifications sent: %s success, %s failure",
                result["success_count"],
                result["failure_count"],
            )
            return result["success_count"]

        except Exception as e:
            logger.error(f"Error in _send_bulk_push_notifications: {str(e)}")
            return 0

    def _clear_multiple_user_caches(self, user_ids):
        """Clear notification cache for multiple users efficiently"""
        try:
            for user_id in user_ids:
                NotificationService.clear_user_notification_cache(str(user_id))

        except Exception as e:
            logger.warning(f"Failed to clear cache for users {user_ids}: {e}")


send_notification_view = (
    SendNotificationAPIView.as_view()
)  # Allow admin to send to all devices
send_notification_view_to_multiple_users = (
    SendNotificationToMultipleUsersAPIView.as_view()
)  # Allow admin to send to multiple users
send_notification_to_recruiters = NewJobApplicationNotificationView.as_view()
