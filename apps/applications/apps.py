from django.apps import AppConfig


class ApplicationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.applications"

    def ready(self):
        """
        Import signals when the app is ready.
        
        This ensures the signal handlers are registered when Django starts up.
        """
        # Import signals to register handlers
        # noinspection PyUnresolvedReferences
        from apps.applications import signals  # noqa: F401

        # Auto-register the daily application report cron job.
        from apps.applications.services import scheduler  # noqa: F401
