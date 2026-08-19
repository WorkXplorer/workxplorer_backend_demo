from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import django_rq
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _

from apps.applications.models.choices import ApplicationStatus
from apps.notifications.models import Notification, NotificationRecipient
from apps.notifications.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class ApplicationNotificationService:
    """Build and dispatch application lifecycle notifications."""

    DEFAULT_LANGUAGE = "uz"
    SUPPORTED_LANGUAGES = {"uz", "ru", "en"}

    @classmethod
    def normalize_language(cls, language: str | None) -> str:
        if language in cls.SUPPORTED_LANGUAGES:
            return language
        return cls.DEFAULT_LANGUAGE

    @classmethod
    def get_user_language(cls, user) -> str:
        return cls.normalize_language(getattr(user, "preferred_language", None))

    @classmethod
    def build_frontend_url(
        cls,
        route: str,
        language: str,
        query_params: dict[str, Any] | None = None,
    ) -> str:
        base_url = getattr(settings, "FRONTEND_URL", "").rstrip("/")
        if not base_url:
            return ""

        normalized_language = cls.normalize_language(language)
        normalized_route = route.strip("/")
        url = f"{base_url}/{normalized_language}/{normalized_route}"

        if query_params:
            query_string = urlencode(
                {key: str(value) for key, value in query_params.items()},
                doseq=True,
            )
            url = f"{url}?{query_string}"

        return url

    @staticmethod
    def get_candidate_full_name(candidate) -> str:
        try:
            profile = candidate.candidateprofile
        except ObjectDoesNotExist:
            profile = None

        if profile and profile.full_name:
            return profile.full_name
        return candidate.email

    @staticmethod
    def get_application_conversation_id(application) -> str | None:
        try:
            return str(application.conversation.id)
        except ObjectDoesNotExist:
            return None

    @classmethod
    def _notification_type_for_status(cls, status: str) -> str:
        if status == ApplicationStatus.OFFER_ACCEPTED:
            return Notification.NotificationType.APPLICATION_ACCEPTED
        if status in {ApplicationStatus.REJECTED, ApplicationStatus.OFFER_REJECTED}:
            return Notification.NotificationType.APPLICATION_REJECTED
        if status == ApplicationStatus.OFFERED:
            return Notification.NotificationType.APPLICATION_OFFERED
        return Notification.NotificationType.APPLICATION_STATUS_UPDATED

    @classmethod
    def create_user_notification(
        cls,
        *,
        user,
        title: str,
        message: str,
        notification_type: str,
        data: dict[str, Any] | None = None,
        created_by=None,
    ) -> Notification:
        notification_data = dict(data or {})

        notification = Notification.objects.create(
            title=title,
            message=message,
            notification_type=notification_type,
            data=notification_data,
            sent_to_all=False,
            created_by=created_by,
        )
        NotificationRecipient.objects.create(notification=notification, user=user)

        # Cache invalidation must happen synchronously so the new notification
        # is visible when the recipient next polls their list.
        NotificationService.clear_user_notification_cache(str(user.id))

        # Offload the Firebase network call to an RQ worker so it doesn't add
        # latency to the current request.  Fall back to synchronous sending only
        # if the queue is unreachable.
        try:
            from apps.notifications.tasks import send_push_notification_task

            django_rq.get_queue("high").enqueue(
                send_push_notification_task,
                notification.id,
                str(user.id),
                title,
                message,
                notification_data,
            )
        except Exception:
            logger.warning(
                "Failed to enqueue push for notification %s — falling back to sync send",
                notification.id,
                exc_info=True,
            )
            push_result = NotificationService.send_to_user(
                user=user,
                notification=notification,
                title=title,
                message=message,
                data=notification_data,
            )
            failure_count = max(
                push_result["devices_count"] - push_result["success_count"], 0
            )
            NotificationService.update_notification_stats(
                notification, push_result["success_count"], failure_count
            )

        return notification

    @classmethod
    def notify_recruiter_new_application(cls, application) -> Notification | None:
        recruiter = getattr(application.vacancy, "created_by", None)
        if recruiter is None:
            return None

        language = cls.get_user_language(recruiter)
        candidate_name = cls.get_candidate_full_name(application.candidate)
        url = cls.build_frontend_url(
            "dashboard/candidates",
            language,
            {
                "page": 0,
                "pageSize": 20,
                "vacancy_id": application.vacancy_id,
            },
        )
        data = {
            "application_id": str(application.id),
            "vacancy_id": str(application.vacancy_id),
            "vacancy_title": application.vacancy.title,
            "candidate_id": str(application.candidate_id),
            "candidate_name": candidate_name,
            "status": application.status,
            "url": url,
            "redirect_url": url,
        }

        return cls.create_user_notification(
            user=recruiter,
            title=_("New application"),
            message=_("%(candidate_name)s applied to %(vacancy_title)s.") % {
                "candidate_name": candidate_name,
                "vacancy_title": application.vacancy.title,
            },
            notification_type=Notification.NotificationType.APPLICATION_APPLIED,
            data=data,
            created_by=application.candidate,
        )

    @classmethod
    def notify_candidate_status_updated(
        cls,
        application,
        *,
        old_status: str,
        new_status: str,
    ) -> Notification:
        candidate = application.candidate
        language = cls.get_user_language(candidate)
        conversation_id = cls.get_application_conversation_id(application)
        url = ""
        if conversation_id:
            url = cls.build_frontend_url(
                "dashboard/chat",
                language,
                {"chat": conversation_id},
            )

        status_display = application.get_status_display(language)
        data = {
            "application_id": str(application.id),
            "vacancy_id": str(application.vacancy_id),
            "vacancy_title": application.vacancy.title,
            "conversation_id": conversation_id or "",
            "old_status": old_status,
            "status": new_status,
            "status_display": status_display,
            "url": url,
            "redirect_url": url,
        }

        return cls.create_user_notification(
            user=candidate,
            title=_("Application status updated"),
            message=_("%(vacancy_title)s status changed to %(status)s.") % {
                "vacancy_title": application.vacancy.title,
                "status": status_display,
            },
            notification_type=cls._notification_type_for_status(new_status),
            data=data,
            created_by=application.last_updated_by,
        )

    @classmethod
    def notify_recruiter_offer_response(cls, application) -> Notification | None:
        recruiter = getattr(application.vacancy, "created_by", None)
        if recruiter is None:
            return None

        candidate_name = cls.get_candidate_full_name(application.candidate)
        language = cls.get_user_language(recruiter)
        conversation_id = cls.get_application_conversation_id(application)
        url = ""
        if conversation_id:
            url = cls.build_frontend_url(
                "dashboard/chat",
                language,
                {"chat": conversation_id},
            )

        if application.status == ApplicationStatus.OFFER_ACCEPTED:
            title = _("Offer accepted")
            message = _("%(candidate_name)s accepted the offer for %(vacancy_title)s.") % {
                "candidate_name": candidate_name,
                "vacancy_title": application.vacancy.title,
            }
            notification_type = Notification.NotificationType.APPLICATION_ACCEPTED
        elif application.status == ApplicationStatus.OFFER_REJECTED:
            title = _("Offer rejected")
            message = _("%(candidate_name)s rejected the offer for %(vacancy_title)s.") % {
                "candidate_name": candidate_name,
                "vacancy_title": application.vacancy.title,
            }
            notification_type = Notification.NotificationType.APPLICATION_REJECTED
        else:
            return None

        data = {
            "application_id": str(application.id),
            "vacancy_id": str(application.vacancy_id),
            "vacancy_title": application.vacancy.title,
            "conversation_id": conversation_id or "",
            "candidate_id": str(application.candidate_id),
            "candidate_name": candidate_name,
            "status": application.status,
            "url": url,
            "redirect_url": url,
        }

        return cls.create_user_notification(
            user=recruiter,
            title=title,
            message=message,
            notification_type=notification_type,
            data=data,
            created_by=application.candidate,
        )
