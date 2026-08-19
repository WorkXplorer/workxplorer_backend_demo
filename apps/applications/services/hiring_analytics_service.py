import logging
from datetime import timedelta
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from apps.applications.models.choices import ApplicationStatus

logger = logging.getLogger(__name__)


class HiringAnalyticsService:
    """Analytics service for hiring-related metrics."""

    @classmethod
    def get_hired_status_keys(cls, company_id=None):
        from apps.applications.models import StatusCategory, ApplicationStatusModel

        keys = {ApplicationStatus.OFFER_ACCEPTED}

        asm_filter = {'category__key': StatusCategory.HIRED, 'is_active': True}
        if company_id:
            asm_filter['company_id'] = company_id

        hired_keys = ApplicationStatusModel.objects.filter(**asm_filter).values_list('key', flat=True)
        keys.update(hired_keys)

        return list(keys)

    @classmethod
    def get_applications_count_for_period(cls, start_date, end_date):
        from apps.applications.models.applications import JobApplication

        return JobApplication.objects.filter(applied_at__range=[start_date, end_date]).count()

    @classmethod
    def get_applications_comparison(cls, current_start, current_end, previous_start, previous_end):
        current_count = cls.get_applications_count_for_period(current_start, current_end)
        previous_count = cls.get_applications_count_for_period(previous_start, previous_end)

        if previous_count == 0:
            percentage_change = None if current_count == 0 else float("inf")
        else:
            percentage_change = ((current_count - previous_count) / previous_count) * 100

        return {
            "current_count": current_count,
            "previous_count": previous_count,
            "percentage_change": percentage_change,
            "absolute_change": current_count - previous_count,
        }

    @classmethod
    def get_hires_count_for_period(cls, start_date, end_date, company_id=None):
        from apps.applications.models.applications import JobApplication

        hired_status_keys = cls.get_hired_status_keys(company_id)

        queryset = JobApplication.objects.filter(
            status__in=hired_status_keys,
            hired_at__range=[start_date, end_date],
        )

        if company_id:
            queryset = queryset.filter(vacancy__company_id=company_id)

        return queryset.count()

    @classmethod
    def get_hiring_dynamics_data(cls, end_date, period_days=30, interval="day", company_id=None):
        from apps.applications.models.applications import JobApplication

        start_date = end_date - timedelta(days=period_days)

        hired_status_keys = cls.get_hired_status_keys(company_id)

        queryset = JobApplication.objects.filter(
            status__in=hired_status_keys,
            hired_at__range=[start_date, end_date],
        )

        if company_id:
            queryset = queryset.filter(vacancy__company_id=company_id)

        trunc_func = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}[interval]

        current_data = (
            queryset.annotate(period=trunc_func("hired_at"))
            .values("period")
            .annotate(hires_count=Count("id"))
            .order_by("period")
        )

        previous_start = start_date - timedelta(days=period_days)
        previous_end = start_date

        previous_queryset = JobApplication.objects.filter(
            status__in=hired_status_keys,
            hired_at__range=[previous_start, previous_end],
        )

        if company_id:
            previous_queryset = previous_queryset.filter(vacancy__company_id=company_id)

        previous_data = (
            previous_queryset.annotate(period=trunc_func("hired_at"))
            .values("period")
            .annotate(hires_count=Count("id"))
            .order_by("period")
        )

        current_series = [
            {"date": item["period"].strftime("%Y-%m-%d"), "count": item["hires_count"]}
            for item in current_data
        ]

        previous_series = [
            {"date": item["period"].strftime("%Y-%m-%d"), "count": item["hires_count"]}
            for item in previous_data
        ]

        current_total = sum(item["count"] for item in current_series)
        previous_total = sum(item["count"] for item in previous_series)

        if previous_total == 0:
            percentage_change = None if current_total == 0 else float("inf")
        else:
            percentage_change = ((current_total - previous_total) / previous_total) * 100

        return {
            "current_period": {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "total_hires": current_total,
                "data_points": current_series,
            },
            "previous_period": {
                "start_date": previous_start.strftime("%Y-%m-%d"),
                "end_date": previous_end.strftime("%Y-%m-%d"),
                "total_hires": previous_total,
                "data_points": previous_series,
            },
            "comparison": {
                "absolute_change": current_total - previous_total,
                "percentage_change": percentage_change,
            },
            "meta": {
                "interval": interval,
                "period_days": period_days,
                "company_id": company_id,
            },
        }
