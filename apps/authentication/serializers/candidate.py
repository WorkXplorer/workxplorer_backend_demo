from rest_framework import serializers
from ..models.candidate import Candidate
import datetime
from ..services.consent_service import ConsentService
from apps.authentication.transitions import resolve_candidate_status, get_status_label
from apps.subscriptions.services import SubscriptionService


class CandidateSerializer(serializers.ModelSerializer):
    is_candidate = serializers.BooleanField(read_only=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    # Single boolean field for all consents
    agreed_to_all_consents = serializers.BooleanField(
        write_only=True,
        required=True,
        help_text="Must be true to agree to all required policies"
    )

    class Meta:
        model = Candidate
        fields = (
            "email",
            "is_candidate",
            "date_of_birth",
            "agreed_to_all_consents",
        )
        extra_kwargs = {
            "date_of_birth": {"required": False, "allow_null": True},
        }

    def validate_date_of_birth(self, value):
        if value and value >= datetime.date.today():
            raise serializers.ValidationError("Date of birth must be in the past.")
        return value

    def validate_agreed_to_all_consents(self, value):
        """Ensure user agreed to all required consents"""
        if not value:
            raise serializers.ValidationError(
                "You must agree to all required policies and terms to register"
            )

        # Validate that required consent configurations exist
        is_valid, error_msg, _ = ConsentService.validate_entity_type('candidate')
        if not is_valid:
            raise serializers.ValidationError(error_msg)

        return value

    def create(self, validated_data):
        # Remove consent agreement flag (not a model field)
        agreed_to_all_consents = validated_data.pop("agreed_to_all_consents", False)

        # Extract optional fields
        date_of_birth = validated_data.pop("date_of_birth", None)

        # Create candidate without password (password will be set via email link)
        candidate = Candidate.objects.create_user(
            email=validated_data["email"],
            password=None,
            is_candidate=True,
            is_active=True,
            date_of_birth=date_of_birth,
        )

        # Auto-assign free subscription
        SubscriptionService.create_candidate_subscription(candidate)

        # Create consent records if user agreed
        if agreed_to_all_consents:
            request = self.context.get('request')
            ip_address = ConsentService.get_client_ip(request)
            user_agent = request.headers.get('User-Agent', '') if request else ''

            ConsentService.create_consents_for_entity(
                consenter=candidate,
                entity_type='candidate',
                ip_address=ip_address,
                user_agent=user_agent
            )

        return candidate


class CandidateStatusSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = ("id", "status", "status_label")

    def get_status(self, obj):
        return resolve_candidate_status(obj)

    def get_status_label(self, obj):
        return get_status_label(resolve_candidate_status(obj))
