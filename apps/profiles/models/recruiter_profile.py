from utils.fields import UUIDField
from django.db import models


class RecruiterProfile(models.Model):
    class Level(models.TextChoices):
        RECRUITER = "Recruiter", "Recruiter"
        ADMIN = "Admin", "Admin"

    id = UUIDField(
        primary_key=True,
        version=7,
        editable=False,
        help_text="Unique identifier for the recruiter profile.",
    )
    recruiter = models.ForeignKey(
        "authentication.Recruiter",
        on_delete=models.CASCADE,
        help_text="Reference to the recruiter user account.",
    )
    full_name = models.CharField(
        max_length=500, null=True, blank=True, help_text="Full name of the recruiter."
    )
    phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Contact phone number of the recruiter.",
    )
    photo = models.ImageField(
        upload_to="recruiter_photos/",
        null=True,
        blank=True,
        help_text="Profile photo of the recruiter.",
    )
    level = models.CharField(
        max_length=20,
        choices=Level.choices,
        default=Level.RECRUITER,
        help_text="Access level of the recruiter (Recruiter or Admin).",
    )

    @property
    def is_admin(self):
        """Check if the recruiter is an admin"""
        return str(self.level).lower() == "admin"

    def __str__(self):
        return f"{self.full_name}"

    class Meta:
        verbose_name = "Recruiter Profile"
        verbose_name_plural = "Recruiter Profiles"
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["recruiter"]),
            models.Index(fields=["full_name"]),
            models.Index(fields=["level"]),
        ]
