from django.apps import AppConfig


class SkillsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.skills"

    def ready(self):
        # Auto-register the daily passive-skill validation cron job.
        import apps.skills.services.scheduler  # noqa: F401
