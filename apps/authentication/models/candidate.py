from django.db import models
from .user import CustomUser


class Candidate(CustomUser):
    """
    Candidate (job seeker) model.
    Inherits from CustomUser with candidate-specific fields.
    """

    edupartner = models.ForeignKey(
        "edupartners.EduPartner",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidates",
        verbose_name="Educational Partner",
        help_text="The educational institution the candidate is associated with",
    )
    faculty = models.ForeignKey(
        "edupartners.Faculty",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="candidates",
        verbose_name="Faculty",
        help_text="The faculty the candidate is associated with",
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Candidate's date of birth for age calculation in analytics",
    )

    is_vault_verified = models.BooleanField(
        default=False,
        help_text="Indicates if the candidate's identity has been verified through Vault",
    )
    onboarding_progress = models.JSONField(
        default=dict,
        blank=True,
        help_text="Tracks completed onboarding steps as {step_code: ISO timestamp}",
    )

    def save(self, *args, **kwargs):
        if not self.pk:
            self.is_candidate = True
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"
