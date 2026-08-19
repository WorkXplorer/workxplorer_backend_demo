from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from utils.fields import UUIDField


class CustomUserManager(BaseUserManager):
    """
    Custom user manager to create users and superusers.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Creates a new user.

        Args:
            email (str): The email address of the user.
            password (str): The password of the user.
            **extra_fields (dict): Additional fields to set on the user.

        Returns:
            CustomUser: The created user.
        """
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Creates a new superuser.

        Args:
            email (str): The email address of the superuser.
            password (str): The password of the superuser.
            **extra_fields (dict): Additional fields to set on the superuser.

        Returns:
            CustomUser: The created superuser.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model to store users and their details.
    """

    id = UUIDField(primary_key=True, version=7, editable=False)
    email = models.EmailField(unique=True)
    phone = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text="Verified phone number in +998XXXXXXXXX format. Usable as an alternate login identifier once verified.",
    )
    phone_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the phone number was confirmed via OTP. Null means unverified.",
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_candidate = models.BooleanField(default=False)
    is_recruiter = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    timezone = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="User's timezone (e.g., 'Asia/Tashkent')"
    )

    class LanguageChoices(models.TextChoices):
        UZ = "uz", "Uzbek"
        RU = "ru", "Russian"
        EN = "en", "English"

    preferred_language = models.CharField(
        max_length=5,
        choices=LanguageChoices.choices,
        default=LanguageChoices.UZ,
        help_text="User's preferred language for notifications and UI.",
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self) -> str:
        return str(self.email)

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["is_candidate"]),
            models.Index(fields=["is_recruiter"]),
            models.Index(fields=["is_active"]),
        ]
