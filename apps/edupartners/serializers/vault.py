from rest_framework import serializers


class VaultRegistrationSerializer(serializers.Serializer):
    """
    Serializer for Vault LMS registration.

    Accepts LMS credentials from the candidate. The candidate ID and
    edupartner ID are derived from the authenticated user.
    """

    lms_login = serializers.CharField(
        max_length=255,
        min_length=3,
        trim_whitespace=True,
        allow_blank=False,
        help_text="The candidate's LMS username",
    )
    lms_password = serializers.CharField(
        max_length=255,
        min_length=3,
        trim_whitespace=True,
        allow_blank=False,
        help_text="The candidate's LMS password",
        write_only=True,
    )
