from rest_framework import serializers
from ..models.user import CustomUser
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext as _


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    user_type = serializers.ChoiceField(
        choices=['candidate', 'recruiter'],
        required=False,
        help_text="Specify user type: 'candidate' or 'recruiter'"
    )
    remember_me = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Set to true to extend session duration"
    )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser

        fields = ("id", "email", "is_candidate", "is_recruiter", "is_active")


class RegisterGeneralUserSerializer(serializers.ModelSerializer):
    """
    Serializer for registering a GeneralUser.
    """

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )

    class Meta:
        model = CustomUser
        fields = ("email", "password", "is_staff", "is_superuser")

    def create(self, validated_data):
        user = CustomUser(
            email=validated_data["email"],
            is_staff=validated_data.get("is_staff", False),
            is_superuser=validated_data.get("is_superuser", False),
            is_active=True,
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


class ResetPasswordRequestSerializer(serializers.Serializer):
    """
    Serializer for requesting a password reset.
    Expects the user's email address to send the reset link.
    """

    # Email address where the reset link will be sent
    email = serializers.EmailField(required=True)


class ResetPasswordConfirmSerializer(serializers.Serializer):
    """
    Serializer for confirming password reset.
    Expects UID, token, and new password confirmation.
    """

    # Encoded user ID
    uid = serializers.CharField(required=True)

    # Token generated for password reset
    token = serializers.CharField(required=True)

    # New password (write-only for security, validated by Django's password validators)
    password = serializers.CharField(
        required=True, write_only=True, validators=[validate_password]
    )

    # Confirmation of the new password (write-only)
    confirm_password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        """
        Ensure that both password fields match.
        Raise a ValidationError if they do not.
        """
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": _("Passwords do not match.")}
            )
        return attrs


class SetPasswordSerializer(serializers.Serializer):
    """
    Unified serializer for password setup after registration (candidate or recruiter).
    The agreed_to_all_consents field is optional here; the view enforces it
    for recruiters after detecting the user type from the UID.
    """

    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    password = serializers.CharField(
        required=True, write_only=True, validators=[validate_password]
    )
    confirm_password = serializers.CharField(required=True, write_only=True)

    # Optional at serializer level — required for recruiters, enforced in the view.
    agreed_to_all_consents = serializers.BooleanField(
        required=False,
        default=False,
        help_text=_("Required for recruiters. Must agree to all policies to activate account."),
    )

    def validate(self, attrs):
        """Ensure that both password fields match."""
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": _("Passwords do not match.")}
            )
        return attrs
