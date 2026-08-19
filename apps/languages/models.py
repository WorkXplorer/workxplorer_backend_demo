from django.db import models
from utils.abstract_model import AbstractBaseModel


class Language(AbstractBaseModel):
    """
    Centralized language model for the platform.

    Stores all available languages for candidates to select when adding
    language proficiency to their resumes. Languages can be added by admins
    and are shared across all resumes.

    Examples: English, Russian, Uzbek, French, German, etc.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Language name (e.g. English, Русский, O'zbek)",
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="ISO 639-1 language code (e.g. en, ru, uz)",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Language"
        verbose_name_plural = "Languages"

    def __str__(self):
        return f"{self.name} ({self.code})"
