# This section is for notifications related to users.
import uuid
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from core.responses import APIResponse

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.core.cache import cache
from django.db.models import Prefetch
from django.contrib.auth import get_user_model

from fcm_django.models import FCMDevice

from apps.notifications.models import Notification, NotificationRecipient
from apps.notifications.serializers import NotificationListResponseSerializer
from apps.notifications.services import NotificationService
from config.pagination import CustomPagination
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

User = get_user_model()
logger = logging.getLogger(__name__)


@extend_schema(
    description=(
            "Retrieve a paginated list of notifications for the authenticated user. "
            "Supports filtering by unread status and notification type. "
            "Results are cached for 5 minutes for efficiency."
    ),
    parameters=[
        OpenApiParameter(
            name="limit",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Number of items to return (default: 20)",
        ),
        OpenApiParameter(
            name="offset",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Number of items to skip before returning results (default: 0)",
        ),
        OpenApiParameter(
            name="only_unread",
            type=OpenApiTypes.BOOL,
            location=OpenApiParameter.QUERY,
            description="If true, only return unread notifications",
        ),
        OpenApiParameter(
            name="type",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filter by notification type",
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=NotificationListResponseSerializer,
            description="Paginated list of notifications for the user",
            examples=[
                OpenApiExample(
                    "Success Example",
                    value={
                        "success": True,
                        "message": "Data retrieved successfully",
                        "data": {
                            "notifications": [
                                {
                                    "id": 12,
                                    "title": "Application Update",
                                    "message": "Your job application has been viewed.",
                                    "created_at": "2025-09-20T12:45:00Z",
                                    "notification_type": "application_accepted",
                                    "is_read": False,
                                    "read_at": None,
                                },
                                {
                                    "id": 13,
                                    "title": "System Alert",
                                    "message": "Scheduled maintenance at 02:00 AM.",
                                    "created_at": "2025-09-21T08:15:00Z",
                                    "notification_type": "platform_announcement",
                                    "is_read": True,
                                    "read_at": "2025-09-21T09:00:00Z",
                                },
                            ],
                            "unread_count": 34,
                        },
                        "pagination": {
                            "count": 100,
                            "next": 2,
                            "previous": None,
                            "limit": 20,
                            "offset": 0,
                        },
                        "timestamp": "2026-02-24T10:00:00+00:00",
                    },
                    status_codes=["200"],
                )
            ],
        ),
        500: OpenApiResponse(
            response=OpenApiTypes.OBJECT,
            description="Server error while fetching notifications",
            examples=[
                OpenApiExample(
                    "Server Error Example",
                    value={"error": "Failed to fetch notifications"},
                    status_codes=["500"],
                )
            ],
        ),
    },
)
class NotificationAPIView(APIView):
    """API endpoint for authenticated users to retrieve their notifications.
    Optimized with caching, pagination, and efficient queries."""

    permission_classes = (IsAuthenticated,)
    pagination_class = CustomPagination

    def get(self, request, *args, **kwargs):
        """Retrieve paginated notifications for the authenticated user with caching.
        1. Extract query parameters for pagination and filtering.
        2. Check cache for existing data.
        3. If not cached, query the database with optimized joins and filters.
        4. Paginate results and prepare response data.
        5. Cache the response data for 5 minutes."""
        user = request.user
        only_unread = request.GET.get("only_unread", "").lower() == "true"
        notification_type = request.GET.get("type")
        paginator = self.pagination_class()
        limit = paginator.get_limit(request)
        if limit is None:
            limit = paginator.default_limit
        offset = paginator.get_offset(request)
        if offset is None:
            offset = 0

        # Cache key
        cache_version = NotificationService.get_user_notification_cache_version(
            str(user.id)
        )
        cache_key = (
            f"notifications_user_{user.id}_limit_{limit}_offset_{offset}"
            f"_unread_{only_unread}_type_{notification_type}_v_{cache_version}"
        )
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        try:
            # Base queryset with optimized joins — fetch only needed columns
            queryset = (
                NotificationRecipient.objects.filter(user=user)
                .select_related("notification")
                .only(
                    "is_read",
                    "read_at",
                    "notification__id",
                    "notification__title",
                    "notification__message",
                    "notification__created_at",
                    "notification__notification_type",
                )
            )

            # Apply filters
            if only_unread:
                queryset = queryset.filter(is_read=False)

            if notification_type:
                queryset = queryset.filter(
                    notification__notification_type=notification_type
                )

            # Order by creation date — uses index if available
            queryset = queryset.order_by("-notification__created_at")

            # Fetch unread count and paginated results in parallel (single DB round-trip)
            # We compute both from the same base queryset to avoid double-filtering
            unread_count = self.get_unread_count(user, queryset if not only_unread else None)

            # Pagination
            notifications_page = paginator.paginate_queryset(queryset, request, view=self)

            # Prepare response data
            notification_list = []
            for n in notifications_page:
                notification_data = {
                    "id": n.notification.id,
                    "title": n.notification.title,
                    "message": n.notification.message,
                    "created_at": n.notification.created_at,
                    "notification_type": n.notification.notification_type,
                    "is_read": n.is_read,
                    "read_at": n.read_at,
                }
                notification_list.append(notification_data)

            response_data = {
                "notifications": notification_list,
                "unread_count": unread_count,
            }
            paginated_response = paginator.get_paginated_response(response_data)

            # Cache for 5 minutes
            cache.set(cache_key, paginated_response.data, 300)

            return paginated_response

        except Exception as e:
            logger.error(f"Error fetching notifications for user {user.id}: {str(e)}")
            return APIResponse.server_error(
                message=_("Failed to fetch notifications")
            )

    def get_unread_count(self, user, prefiltered_queryset=None):
        """Get unread notifications count for user.

        Uses cache first, then falls back to database COUNT.
        When prefiltered_queryset is provided (e.g. type-filtered),
        the cache key incorporates the filter to avoid cache poisoning.
        """
        cache_key = f"unread_count_user_{user.id}"
        if prefiltered_queryset is not None:
            cache_key += "_filtered"
        unread_count = cache.get(cache_key)

        if unread_count is None:
            if prefiltered_queryset is not None:
                unread_count = prefiltered_queryset.filter(is_read=False).count()
            else:
                unread_count = NotificationRecipient.objects.filter(
                    user=user, is_read=False
                ).count()
            cache.set(cache_key, unread_count, 300)

        return unread_count


@extend_schema(
    description="Mark a specific notification as read for the authenticated user.",
    parameters=[
        OpenApiParameter(
            name="notification_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="ID of the notification to mark as read",
            required=True,
            examples=[OpenApiExample("Example ID", value=123)],
        )
    ],
    request=None,
    responses={
        200: OpenApiResponse(
            description="Notification successfully marked as read",
            examples=[
                OpenApiExample(
                    "Success Example",
                    value={"message": "Notification marked as read"},
                )
            ],
        ),
        404: OpenApiResponse(
            description="Notification not found for this user",
            examples=[
                OpenApiExample(
                    "Not Found Example",
                    value={"error": "Notification not found"},
                )
            ],
        ),
        401: OpenApiResponse(
            description="Unauthorized (missing or invalid token)",
            examples=[
                OpenApiExample(
                    "Unauthorized Example",
                    value={"detail": "Authentication credentials were not provided."},
                )
            ],
        ),
    },
)
class NotificationMarkAsReadAPIView(APIView):
    """API endpoint to mark notification as read."""

    permission_classes = (IsAuthenticated,)

    def patch(self, request, notification_id):
        """Mark a specific notification as read for the authenticated user.
        1. Validate notification ID and ownership.
        2. Update read status and timestamp.
        3. Invalidate relevant cache entries."""
        user = request.user

        try:
            notification_recipient = NotificationRecipient.objects.select_related(
                "notification"
            ).get(notification_id=notification_id, user=user)

            notification_recipient.mark_as_read()

            NotificationService.clear_user_notification_cache(str(user.id))

            return APIResponse.success(message=_("Notification marked as read"))

        except NotificationRecipient.DoesNotExist:
            return APIResponse.not_found(message=_("Notification not found"))


@extend_schema(
    description=(
        "Mark **all unread notifications** as read for the authenticated user. "
        "Optionally pass `notification_ids` in the request body to mark only "
        "specific notifications. When `notification_ids` is omitted or empty, "
        "all unread notifications are marked as read."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "notification_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Optional list of notification IDs to mark as read. "
                        "If omitted or empty, all unread notifications are marked."
                    ),
                }
            },
        }
    },
    responses={
        200: OpenApiResponse(
            description="Successfully marked notifications as read",
            examples=[
                OpenApiExample(
                    "Success Example",
                    value={
                        "message": "5 notifications marked as read",
                        "updated_count": 5,
                    },
                )
            ],
        ),
        500: OpenApiResponse(
            description="Server error while marking notifications as read",
            examples=[
                OpenApiExample(
                    "Error Example",
                    value={"error": "Failed to mark notifications as read"},
                )
            ],
        ),
        401: OpenApiResponse(
            description="Unauthorized (missing or invalid token)",
            examples=[
                OpenApiExample(
                    "Unauthorized Example",
                    value={"detail": "Authentication credentials were not provided."},
                )
            ],
        ),
    },
)
class NotificationBulkMarkAsReadAPIView(APIView):
    """API endpoint to mark notifications as read in bulk.

    Supports two modes:
    1. Full bulk: PATCH without body → marks ALL unread notifications as read
    2. Selective bulk: PATCH with {"notification_ids": [1, 2, 3]} → marks only
       those specific notifications (must belong to the authenticated user)
    """

    permission_classes = (IsAuthenticated,)

    def patch(self, request):
        """Mark unread notifications as read for the authenticated user.

        Accepts an optional JSON body with 'notification_ids' for selective
        bulk marking. Falls back to marking all unread notifications when
        no IDs are provided.

        Returns updated_count of actually changed rows.
        """
        user = request.user

        try:
            notification_ids = self._get_notification_ids(request)

            if notification_ids is None:
                # No notification_ids key at all → mark ALL unread
                updated_count = self._mark_all_as_read(user)
            elif notification_ids:
                # Specific IDs provided → mark only those
                updated_count = self._mark_specific_as_read(user, notification_ids)
            else:
                # Empty list explicitly provided → no-op
                updated_count = 0

            NotificationService.clear_user_notification_cache(str(user.id))

            return APIResponse.success(
                data={"updated_count": updated_count},
                message=f"{updated_count} notifications marked as read",
            )

        except Exception as e:
            logger.error(
                f"Error marking notifications as read for user {user.id}: {str(e)}"
            )
            return APIResponse.server_error(
                message=_("Failed to mark notifications as read")
            )

    def _get_notification_ids(self, request):
        """Extract and validate notification_ids from request body.

        Returns None if no IDs provided (meaning 'mark all').
        Returns a list of integers if valid IDs provided.
        Returns an empty list if body has empty notification_ids (no-op).
        """
        body = request.data if hasattr(request, "data") else {}
        if not body:
            return None

        ids = body.get("notification_ids")
        if ids is None:
            return None

        if not isinstance(ids, list):
            return None

        if len(ids) == 0:
            return []

        # Validate and deduplicate integer IDs
        valid_ids = []
        seen = set()
        for nid in ids:
            try:
                int_id = int(nid)
                if int_id > 0 and int_id not in seen:
                    valid_ids.append(int_id)
                    seen.add(int_id)
            except (TypeError, ValueError):
                # Ignore malformed notification IDs and continue processing
                # the rest of the list to keep parsing fault-tolerant.
                logger.debug("Ignoring invalid notification_id value: %r", nid)

        return valid_ids

    def _mark_specific_as_read(self, user, notification_ids):
        """Mark specific notification_ids as read for the given user.

        Uses a single bulk UPDATE filtered by user + notification_id__in.
        Only updates rows where is_read=False to get accurate count.
        """
        return NotificationRecipient.objects.filter(
            user=user,
            notification_id__in=notification_ids,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

    def _mark_all_as_read(self, user):
        """Mark all unread notifications as read for the given user."""
        return NotificationRecipient.objects.filter(
            user=user, is_read=False
        ).update(is_read=True, read_at=timezone.now())


class SendNotificationToUserAPIView(APIView):
    """API endpoint for admin users to send push notifications to a specific user.
    Only accessible by admin users.

    Example request payload:
    {"user_id": "123e4567-e89b-12d3-a456-426614174000",
        "title": "Personal Message",
        "message": "You have a new job match!",
        "notification_type": "new_job_match",
        "data": {
            "job_id": "456",
            "redirect_url": "/jobs/456"}
    }"""

    permission_classes = (IsAuthenticated, IsAdminUser)

    @extend_schema(
        summary="Send notification to a specific user",
        description="Admin user sends push notification to a specific user",
        request={
            "application/json": {
                "type": "object",
                "required": ["user_id", "title", "message"],
                "properties": {
                    "user_id": {"type": "string", "format": "uuid"},
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
                        "user_id": {"type": "string", "format": "uuid"},
                        "user_email": {"type": "string"},
                        "push_notification_sent": {"type": "boolean"},
                        "push_notification_message": {"type": "string"},
                        "devices_count": {"type": "integer"},
                        "success_count": {"type": "integer"},
                        "failure_count": {"type": "integer"},
                    },
                },
                description="Notification sent successfully",
            ),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="User Not Found"),
            500: OpenApiResponse(description="Internal Server Error"),
        },
    )
    def post(self, request, *args, **kwargs):
        """Send a push notification to a specific user.
        1. Validate input data.
        2. Fetch user and their active devices.
        3. Create notification and recipient records.
        4. Send push notification using batch processing.
        5. Update notification stats and clear relevant caches."""
        # Extract data from request
        user_id = request.data.get("user_id")
        title = request.data.get("title")
        message_text = request.data.get("message")
        notification_type = request.data.get(
            "notification_type", Notification.NotificationType.PLATFORM_ANNOUNCEMENT
        )
        data = request.data.get("data", {})

        # Validate required fields
        if not all([user_id, title, message_text]):
            return APIResponse.bad_request(
                message=_("user_id, title, and message are required.")
            )

        # Validate UUID format
        try:
            uuid.UUID(str(user_id))
        except ValueError:
            return APIResponse.bad_request(
                message=_("Invalid user_id format. Must be a valid UUID.")
            )

        # Validate notification type
        valid_types = [choice[0] for choice in Notification.NotificationType.choices]
        if notification_type not in valid_types:
            return APIResponse.bad_request(
                message=f"Invalid notification_type. Must be one of: {valid_types}"
            )

        try:
            with transaction.atomic():
                user = (
                    User.objects.select_related()
                    .filter(id=user_id, is_active=True)
                    .prefetch_related(
                        Prefetch(
                            "fcmdevice_set",
                            queryset=FCMDevice.objects.filter(active=True),
                            to_attr="active_devices",
                        )
                    )
                    .first()
                )

                if not user:
                    return APIResponse.not_found(
                        message=_("User not found or inactive.")
                    )

                active_devices = user.active_devices
                if not active_devices:
                    return APIResponse.bad_request(
                        message=_("No active devices found for user.")
                    )

                devices_count = len(active_devices)
                notification = Notification.objects.create(
                    title=title,
                    message=message_text,
                    notification_type=notification_type,
                    data=data,
                    sent_to_all=False,
                    created_by=request.user,
                    sent_count=1,  # Set initial count
                    success_count=0,  # Will be updated after push notification
                    failure_count=0,
                )

                NotificationRecipient.objects.create(
                    notification=notification, user=user
                )

                push_result = self._send_push_notification_bulk(
                    active_devices, notification, title, message_text, data
                )

                Notification.objects.filter(id=notification.id).update(
                    sent_count=devices_count,
                    success_count=push_result["success_count"],
                    failure_count=push_result["failure_count"],
                    updated_at=timezone.now(),
                )

                # Clear user's notification cache asynchronously if possible
                self._clear_user_notification_cache_async(user.id)

                return APIResponse.success(
                    data={
                        "notification_id": notification.id,
                        "user_id": str(user.id),
                        "user_email": user.email,
                        "push_notification_sent": push_result["success"],
                        "push_notification_message": push_result["message"],
                        "devices_count": devices_count,
                        "success_count": push_result["success_count"],
                        "failure_count": push_result["failure_count"],
                    },
                    message=_("Notification sent successfully."),
                )

        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {str(e)}")
            return APIResponse.server_error(
                message=_("Failed to send notification. Please try again.")
            )

    def _send_push_notification_bulk(
            self, devices, notification, title, message_text, data
    ):
        """Send push notification to multiple devices using the shared notification service."""
        try:
            if not devices:
                return {
                    "success": False,
                    "message": "No active devices found",
                    "success_count": 0,
                    "failure_count": 0,
                }

            success_count = 0
            failure_count = 0
            total_devices = len(devices)

            # Prepare message data once
            message_data = {
                "notification_id": str(notification.id),
                "notification_type": notification.notification_type,
                "timestamp": str(notification.created_at),
                **data,
            }

            # Convert data values to strings once
            string_data = {k: str(v) for k, v in message_data.items()}

            result = NotificationService.send_to_devices(
                list(devices), title, message_text, string_data
            )
            success_count = result["success_count"]
            failure_count = result["failure_count"]

            return {
                "success": success_count > 0,
                "message": f"Sent to {success_count} out of {total_devices} devices",
                "success_count": success_count,
                "failure_count": failure_count,
            }

        except Exception as e:
            logger.error(f"Error in _send_push_notification_bulk: {str(e)}")
            return {
                "success": False,
                "message": f"Push notification failed: {str(e)}",
                "success_count": 0,
                "failure_count": len(devices),
            }

    def _clear_user_notification_cache_async(self, user_id):
        """Clear user's notification related cache asynchronously"""
        try:
            NotificationService.clear_user_notification_cache(str(user_id))
        except Exception as e:
            logger.warning(f"Failed to clear cache for user {user_id}: {e}")


get_notification_view = NotificationAPIView.as_view()
mark_as_read_view = NotificationMarkAsReadAPIView.as_view()
bulk_mark_as_read_view = NotificationBulkMarkAsReadAPIView.as_view()
send_notification_to_user_view = SendNotificationToUserAPIView.as_view()
