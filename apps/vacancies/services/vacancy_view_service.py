"""
Service for tracking vacancy views with intelligent deduplication.

This service ensures that only one VacancyView record is created per candidate
per vacancy within a configurable cooldown period, avoiding unnecessary
database writes while maintaining accurate analytics.
"""

from datetime import timedelta
from django.utils import timezone
from django.conf import settings

from apps.vacancies.models import VacancyView


# Default cooldown period in minutes (can be overridden in settings)
DEFAULT_VIEW_COOLDOWN_MINUTES = getattr(
    settings, "VACANCY_VIEW_COOLDOWN_MINUTES", 60
)


class VacancyViewService:
    """
    Handles vacancy view tracking with time-based deduplication.
    """

    @staticmethod
    def record_view(vacancy, candidate, cooldown_minutes=None):
        """
        Record a vacancy view, avoiding duplicate records within the cooldown period.

        Args:
            vacancy: The Vacancy instance being viewed
            candidate: The Candidate viewing the vacancy
            cooldown_minutes: Optional custom cooldown period (defaults to settings)

        Returns:
            tuple: (VacancyView instance, bool created)
                - The view record (existing or newly created)
                - True if a new record was created, False if existing was returned
        """
        if cooldown_minutes is None:
            cooldown_minutes = DEFAULT_VIEW_COOLDOWN_MINUTES

        cooldown_threshold = timezone.now() - timedelta(minutes=cooldown_minutes)

        # Check for a recent view within the cooldown period
        recent_view = VacancyView.objects.filter(
            vacancy=vacancy,
            candidate=candidate,
            viewed_at__gte=cooldown_threshold,
        ).order_by("-viewed_at").first()

        if recent_view:
            # Return existing view without creating a new record
            return recent_view, False

        # Create a new view record
        new_view = VacancyView.objects.create(
            vacancy=vacancy,
            candidate=candidate,
        )
        return new_view, True

    @staticmethod
    def get_view_count(vacancy, unique_only=True):
        """
        Get the view count for a vacancy.

        Args:
            vacancy: The Vacancy instance
            unique_only: If True, count unique candidates only

        Returns:
            int: The view count
        """
        queryset = VacancyView.objects.filter(vacancy=vacancy)

        if unique_only:
            return queryset.values("candidate").distinct().count()
        return queryset.count()

    @staticmethod
    def has_candidate_viewed(vacancy, candidate):
        """
        Check if a candidate has ever viewed a vacancy.

        Args:
            vacancy: The Vacancy instance
            candidate: The Candidate instance

        Returns:
            bool: True if the candidate has viewed the vacancy
        """
        return VacancyView.objects.filter(
            vacancy=vacancy,
            candidate=candidate,
        ).exists()
