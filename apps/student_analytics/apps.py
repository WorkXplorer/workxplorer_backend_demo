from django.apps import AppConfig


class StudentAnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.student_analytics"

    def ready(self):
        import apps.student_analytics.signals  # noqa: F401
