from rest_framework import serializers
from django.utils.translation import gettext as _


class AccountDeleteSerializer(serializers.Serializer):
    """
    Serializer for self-service account deletion.

    The account owner must explicitly confirm, and — when the account has a
    usable password — re-enter that password. Accounts created through Google
    or phone OTP have no usable password, so for them the confirmation flag
    alone is the check.
    """

    confirm = serializers.BooleanField(
        required=True,
        help_text=_("Must be true. Confirms the account deletion is intentional."),
    )
    password = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text=_("Current password. Required for accounts that have one."),
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        help_text=_("Optional reason for leaving."),
    )

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError(
                _("You must confirm that you want to delete your account.")
            )
        return value

    def validate(self, attrs):
        user = self.context["request"].user

        if user.has_usable_password():
            password = attrs.get("password")
            if not password:
                raise serializers.ValidationError(
                    {"password": _("Enter your password to confirm deletion.")}
                )
            if not user.check_password(password):
                raise serializers.ValidationError(
                    {"password": _("Incorrect password.")}
                )

        return attrs
