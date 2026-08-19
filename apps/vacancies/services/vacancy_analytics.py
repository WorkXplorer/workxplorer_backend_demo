import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from django.utils import timezone

logger = logging.getLogger(__name__)


class VacancyAnalyticsService:
    """
    Service for calculating vacancy-specific analytics metrics.

    Provides methods to calculate:
    - Time to hire (average days from application to hiring)
    - Overall conversion rate (hired / total applications)
    - Vacancy views count
    - Vacancy responses count
    """

    # Application status constants
    STATUS_HIRED = "hired"

    def __init__(self, vacancy_id: UUID, company_id: UUID):
        """
        Initialize the vacancy analytics service.

        Args:
            vacancy_id: UUID of the vacancy to analyze
            company_id: UUID of the company (for data isolation)
        """
        self.vacancy_id = vacancy_id
        self.company_id = company_id

    @staticmethod
    def get_period_dates(
            period_type: str = "month", reference_date: Optional[datetime] = None
    ) -> tuple[datetime, datetime, datetime, datetime]:
        """
        Calculate current and previous period date ranges.

        Args:
            period_type: One of 'day', 'week', 'month', 'year'
            reference_date: Reference date for calculations (defaults to now)

        Returns:
            Tuple of (current_start, current_end, previous_start, previous_end)
        """
        if reference_date is None:
            reference_date = timezone.now()

        if period_type == "day":
            current_start = reference_date.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            current_end = reference_date
            previous_start = current_start - timedelta(days=1)
            previous_end = current_start
        elif period_type == "week":
            days_since_monday = reference_date.weekday()
            current_start = (
                    reference_date - timedelta(days=days_since_monday)
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            current_end = reference_date
            previous_start = current_start - timedelta(weeks=1)
            previous_end = current_start
        elif period_type == "month":
            current_start = reference_date.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            current_end = reference_date
            previous_end = current_start
            previous_start = (current_start - timedelta(days=1)).replace(day=1)
        elif period_type == "year":
            current_start = reference_date.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            current_end = reference_date
            previous_start = current_start.replace(year=current_start.year - 1)
            previous_end = current_start
        else:
            raise ValueError(f"Invalid period_type: {period_type}")

        return current_start, current_end, previous_start, previous_end

    def calculate_time_to_hire(
            self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """
        Calculate average Time to Hire for the vacancy.

        Time to hire = Date of 'Hired' status - Date of first application

        Args:
            start_date: Start of the analysis period
            end_date: End of the analysis period

        Returns:
            Dictionary with TTH metrics
        """
        from apps.applications.models import JobApplication

        # Get all hired applications for this vacancy within the period
        hired_applications = JobApplication.objects.filter(
            vacancy_id=self.vacancy_id,
            vacancy__company_id=self.company_id,
            status=self.STATUS_HIRED,
            hired_at__gte=start_date,
            hired_at__lte=end_date,
            hired_at__isnull=False,
            created_at__isnull=False,
        )

        # Calculate average TTH in days
        hired_count = hired_applications.count()
        if hired_count > 0:
            total_days = sum(
                (app.hired_at - app.created_at).days
                for app in hired_applications
            )
            avg_tth_days = total_days / hired_count
        else:
            avg_tth_days = None

        return {
            "average_days": (
                round(avg_tth_days, 1) if avg_tth_days is not None else None
            ),
            "hired_count": hired_count,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

    def calculate_overall_conversion(
            self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """
        Calculate overall conversion rate for the vacancy.

        Conversion = (Hired candidates / Total responses) × 100%
        """
        from apps.applications.models import JobApplication

        # Total applications for this vacancy
        total_applications = JobApplication.objects.filter(
            vacancy_id=self.vacancy_id,
            vacancy__company_id=self.company_id,
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).count()

        # Hired applications
        hired_applications = JobApplication.objects.filter(
            vacancy_id=self.vacancy_id,
            vacancy__company_id=self.company_id,
            status=self.STATUS_HIRED,
            hired_at__gte=start_date,
            hired_at__lte=end_date,
            hired_at__isnull=False,
        ).count()

        # Calculate conversion rate
        if total_applications > 0:
            conversion_rate = (hired_applications / total_applications) * 100
        else:
            conversion_rate = 0.0

        return {
            "conversion_rate": round(conversion_rate, 1),
            "hired_count": hired_applications,
            "total_applications": total_applications,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

    def calculate_vacancy_views(
            self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """
        Calculate total vacancy views for the period.
        """
        from apps.vacancies.models import VacancyView

        views_qs = VacancyView.objects.filter(
            vacancy_id=self.vacancy_id,
            vacancy__company_id=self.company_id,
            viewed_at__gte=start_date,
            viewed_at__lte=end_date,
        )

        views_count = views_qs.count()

        # Unique viewers (distinct candidates)
        unique_viewers = views_qs.values("candidate_id").distinct().count()

        return {
            "total_views": views_count,
            "unique_viewers": unique_viewers,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

    def calculate_vacancy_responses(
            self, start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """
        Calculate total vacancy responses (applications) for the period.
        """
        from apps.applications.models import JobApplication

        responses_count = JobApplication.objects.filter(
            vacancy_id=self.vacancy_id,
            vacancy__company_id=self.company_id,
            created_at__gte=start_date,
            created_at__lte=end_date,
        ).count()

        return {
            "total_responses": responses_count,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

    @staticmethod
    def calculate_change_percentage(
            current_value: Optional[float], previous_value: Optional[float]
    ) -> dict[str, Any]:
        """
        Calculate percentage change between two values.
        """
        if current_value is None or previous_value is None:
            return {"change_percentage": None, "change_direction": None}

        if previous_value == 0:
            if current_value > 0:
                return {"change_percentage": 100.0, "change_direction": "up"}
            return {"change_percentage": 0.0, "change_direction": "neutral"}

        change = ((current_value - previous_value) / previous_value) * 100
        direction = "up" if change > 0 else ("down" if change < 0 else "neutral")

        return {
            "change_percentage": round(abs(change), 1),
            "change_direction": direction,
        }

    def get_all_metrics(
            self, period_type: str = "month", reference_date: Optional[datetime] = None
    ) -> dict[str, Any]:
        """
        Calculate all four vacancy metrics with period comparison.
        """
        from apps.vacancies.models import Vacancy

        current_start, current_end, previous_start, previous_end = (
            self.get_period_dates(period_type, reference_date)
        )

        try:
            vacancy = Vacancy.objects.select_related("company").get(
                id=self.vacancy_id, company_id=self.company_id
            )
        except Vacancy.DoesNotExist:
            logger.error(
                f"Vacancy {self.vacancy_id} not found for company {self.company_id}"
            )
            return {}

        # Calculate current period metrics
        current_tth = self.calculate_time_to_hire(current_start, current_end)
        current_conversion = self.calculate_overall_conversion(
            current_start, current_end
        )
        current_views = self.calculate_vacancy_views(current_start, current_end)
        current_responses = self.calculate_vacancy_responses(current_start, current_end)

        # Calculate previous period metrics
        previous_tth = self.calculate_time_to_hire(previous_start, previous_end)
        previous_conversion = self.calculate_overall_conversion(
            previous_start, previous_end
        )
        previous_views = self.calculate_vacancy_views(previous_start, previous_end)
        previous_responses = self.calculate_vacancy_responses(
            previous_start, previous_end
        )

        # Calculate changes
        tth_change = self.calculate_change_percentage(
            current_tth["average_days"], previous_tth["average_days"]
        )
        conversion_change = self.calculate_change_percentage(
            current_conversion["conversion_rate"],
            previous_conversion["conversion_rate"],
        )
        views_change = self.calculate_change_percentage(
            current_views["total_views"], previous_views["total_views"]
        )
        responses_change = self.calculate_change_percentage(
            current_responses["total_responses"], previous_responses["total_responses"]
        )

        return {
            "vacancy_id": str(self.vacancy_id),
            "vacancy_title": vacancy.title,
            "company_id": str(self.company_id),
            "company_name": vacancy.company.name if vacancy.company else None,
            "domain_id": str(vacancy.domain_id) if vacancy.domain_id else None,
            "period_type": period_type,
            "generated_at": timezone.now().isoformat(),
            "metrics": {
                "time_to_hire": {
                    "value": current_tth["average_days"],
                    "unit": "days",
                    "hired_count": current_tth["hired_count"],
                    "change": tth_change,
                    "label": "Time to hire",
                },
                "overall_conversion": {
                    "value": current_conversion["conversion_rate"],
                    "unit": "percent",
                    "hired_count": current_conversion["hired_count"],
                    "total_applications": current_conversion["total_applications"],
                    "change": conversion_change,
                    "label": "Общая конверсия",
                },
                "vacancy_views": {
                    "value": current_views["total_views"],
                    "unique_viewers": current_views["unique_viewers"],
                    "change": views_change,
                    "label": "Кол-во просмотров вакансии",
                },
                "vacancy_responses": {
                    "value": current_responses["total_responses"],
                    "change": responses_change,
                    "label": "Кол-во откликов",
                },
            },
            "period": {
                "current": {
                    "start": current_start.isoformat(),
                    "end": current_end.isoformat(),
                },
                "previous": {
                    "start": previous_start.isoformat(),
                    "end": previous_end.isoformat(),
                },
            },
        }


def calculate_vacancy_specific_metrics(
        vacancy_id: str,
        company_id: str,
        period_type: str = "month",
        reference_date: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Standalone function to calculate vacancy-specific metrics.
    Used by the webhook sender for periodic data sending.

    Args:
        vacancy_id: UUID string of the vacancy
        company_id: UUID string of the company
        period_type: One of 'day', 'week', 'month', 'year'
        reference_date: Reference date for calculations

    Returns:
        Dictionary with all vacancy metrics
    """
    from uuid import UUID

    service = VacancyAnalyticsService(
        vacancy_id=UUID(vacancy_id), company_id=UUID(company_id)
    )
    return service.get_all_metrics(
        period_type=period_type, reference_date=reference_date
    )
