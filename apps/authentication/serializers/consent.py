from rest_framework import serializers
from ..models.consent import UserConsent


class ConsentReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for viewing consent records"""

    consenter_type = serializers.SerializerMethodField()
    consenter_identifier = serializers.SerializerMethodField()

    class Meta:
        model = UserConsent
        fields = [
            'id',
            'consenter_type',
            'consenter_identifier',
            'consent_type',
            'version',
            'agreed_at',
            'ip_address',
            'withdrawn_at'
        ]
        read_only_fields = fields

    def get_consenter_type(self, obj):
        """Return the type of entity that gave consent"""
        return obj.content_type.model

    def get_consenter_identifier(self, obj):
        """Return identifier (email for users, name for companies)"""
        if hasattr(obj.consenter, 'email'):
            return obj.consenter.email
        elif hasattr(obj.consenter, 'name'):
            return obj.consenter.name
        return str(obj.object_id)


class AgreementSerializer(serializers.Serializer):
    """
    Simple serializer for consent agreement.
    Frontend sends a single boolean to agree to ALL required consents.
    """

    agreed_to_all_consents = serializers.BooleanField(
        required=True,
        help_text="Must be true to agree to all required policies and terms"
    )

    def validate_agreed_to_all_consents(self, value):
        """Ensure user actually agreed"""
        if not value:
            raise serializers.ValidationError(
                "You must agree to all required policies and terms to continue"
            )
        return value
