from django.db import models
from django.utils.translation import gettext_lazy as _

from utils.fields import UUIDField
from utils import AbstractBaseModel


class Citizenship(AbstractBaseModel):
    """
    Citizenship model with multilingual support (en, ru, uz).
    Linked to CandidateProfile to store candidate's citizenship.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    name = models.CharField(
        max_length=100,
        verbose_name=_("Citizenship name"),
        help_text=_("Name of the citizenship/country"),
    )

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = _("Citizenship")
        verbose_name_plural = _("Citizenships")
        ordering = ["name"]
