from .analytics import EduPartnerAnalyticsService


def schedule_edupartner_analytics(*args, **kwargs):
    from .scheduler import schedule_edupartner_analytics as schedule

    return schedule(*args, **kwargs)

__all__ = [
    "EduPartnerAnalyticsService",
    "schedule_edupartner_analytics",
]
