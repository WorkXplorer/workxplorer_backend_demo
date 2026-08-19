from django.apps import AppConfig


class EdupartnersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.edupartners"

    def ready(self):
        """
        Initialize RQ scheduler when the application starts.
        Import scheduler to auto-schedule periodic tasks.
        """
        import apps.edupartners.services.scheduler
