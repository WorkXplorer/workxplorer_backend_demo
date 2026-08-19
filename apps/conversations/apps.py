from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.conversations"

    def ready(self):
        """Register signals and startup checks when the app is ready."""
        import apps.conversations.signals  # noqa: F401
        import apps.conversations.checks  # noqa: F401
