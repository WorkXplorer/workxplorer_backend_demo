from django.db import models
from .user import CustomUser
from django.core.validators import FileExtensionValidator
from utils.fields import UUIDField
from utils.abstract_model import AbstractBaseModel


class Company(AbstractBaseModel):
    """
    Company model to store company essential data.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    name = models.CharField(max_length=255)
    domain = models.ForeignKey(
        "domain.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies",
        help_text="Company specialization domain",
    )
    tin = models.CharField(max_length=9, unique=True)
    file = models.FileField(
        upload_to="company_files/",
        null=True,
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "doc", "docx", "zip"])
        ],
    )
    is_active = models.BooleanField(default=False)

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["tin"]),
        ]


class Recruiter(CustomUser):
    """
    Recruiter model to store recruiter login details.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="recruiters",
        null=True,
        blank=True,
    )
    is_waiting_approval = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.is_recruiter = True
        super().save(*args, **kwargs)

    class Meta:  # type: ignore
        verbose_name = "Recruiter"
        verbose_name_plural = "Recruiters"
