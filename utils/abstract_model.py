from django.db import models
from django.utils.translation import gettext_lazy as _


class AbstractBaseModel(models.Model):
    """
    An abstract base model that provides common fields for all models.
    This model includes fields for tracking creation and update timestamps.
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        abstract = True
