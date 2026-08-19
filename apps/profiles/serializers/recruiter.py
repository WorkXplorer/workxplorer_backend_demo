from rest_framework import serializers
from django.utils.translation import gettext as _
from apps.profiles.models import CompanyProfile, RecruiterProfile
from apps.authentication.models import Company, Recruiter

from utils import FlexibleImageField, validate_uploaded_file


class RecruiterListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing recruiters in the same company.
    Excludes company information since all recruiters belong to the same company.
    """
    id = serializers.UUIDField(source="recruiter.id", format="hex_verbose", read_only=True)
    photo = FlexibleImageField(required=False, allow_null=True)
    email = serializers.EmailField(source="recruiter.email", read_only=True)

    class Meta:
        model = RecruiterProfile
        fields = (
            "id",
            "full_name",
            "email",
            "phone",
            "photo",
            "level",
        )


class RecruiterProfileSerializer(serializers.ModelSerializer):
    company = serializers.SerializerMethodField()
    photo = FlexibleImageField(required=False, allow_null=True)

    company_address = serializers.CharField(
        required=False, allow_null=True, write_only=True, source="*"
    )
    email = serializers.EmailField(source="recruiter.email", read_only=True)

    class Meta:
        model = RecruiterProfile
        fields = (
            "id",
            "recruiter",
            "email",
            "company",
            "company_address",
            "full_name",
            "phone",
            "photo",
            "level",
        )

    def get_company(self, obj) -> dict | None:
        # Return a serializable representation of the company
        company = obj.recruiter.company
        profiles = getattr(company, "companyprofile", None)
        profile = next(iter(profiles.all()), None) if profiles else None

        if company:
            return {
                "id": str(company.id),  # Convert UUID to string
                "name": company.name,
                "tin": company.tin,
                "address": getattr(profile, "address", None),
                "is_active": company.is_active,
            }
        return None

    def validate_photo(self, value):
        return validate_uploaded_file(value, allow_string=True)

    def update(self, instance, validated_data):
        company_address = validated_data.pop("company_address", None)

        # Handle photo field carefully
        if 'photo' in validated_data:
            photo = validated_data['photo']

            if photo is None:
                # Photo explicitly sent as None/empty - delete existing photo
                if instance.photo:
                    # Delete old photo file from storage
                    instance.photo.delete(save=False)
                validated_data['photo'] = None
            elif isinstance(photo, str):
                # If a string path, assign directly (existing photo URL)
                instance.photo = photo
                validated_data.pop('photo')
            # else: photo is a file upload, let it process normally
        # If 'photo' not in validated_data, keep existing photo (no change)

        updated_instance = super().update(instance, validated_data)
        if company_address is not None:
            # Update or create CompanyProfile with the new address
            company = updated_instance.recruiter.company
            if company:
                profile, created = CompanyProfile.objects.get_or_create(company=company)
                profile.address = company_address
                profile.save()

        return updated_instance


class RecruiterLevelUpdateSerializer(serializers.Serializer):
    level = serializers.ChoiceField(
        choices=RecruiterProfile.Level.choices,
        required=True,
        error_messages={
            "invalid_choice": "Level must be either Recruiter or Admin."
        },
    )

    def validate_level(self, value):
        """Level validation"""
        valid_levels = dict(RecruiterProfile.Level.choices).keys()
        if value not in valid_levels:
            raise serializers.ValidationError(
                f"Invalid level. Allowed levels are: {', '.join(valid_levels)}"
            )
        return value


class AdminRecruiterRegistrationSerializer(serializers.Serializer):
    """
    Serializer for admin-only recruiter registration.
    Creates both Recruiter and RecruiterProfile with full details.
    Uses Django's set_password for secure password handling.
    """

    # Recruiter model fields
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Password will be hashed using Django's set_password() with Django's default PBKDF2 password hasher"
    )
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(),
        required=True,
        help_text="Company UUID that this recruiter belongs to"
    )

    # RecruiterProfile fields
    full_name = serializers.CharField(
        max_length=500,
        required=True,
        help_text="Full name of the recruiter"
    )
    phone_number = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="Phone number of the recruiter"
    )
    photo = FlexibleImageField(
        required=False,
        allow_null=True,
        help_text="Profile photo of the recruiter"
    )
    level = serializers.ChoiceField(
        choices=RecruiterProfile.Level.choices,
        default=RecruiterProfile.Level.RECRUITER,
        help_text="Access level: Recruiter or Admin"
    )

    def validate_photo(self, value):
        return validate_uploaded_file(value)

    def validate_email(self, value):
        """Check if email already exists for new recruiters."""
        # For updates, we skip this check if it's the same email
        instance = self.context.get('instance')
        if instance:
            if Recruiter.objects.filter(email=value).exclude(id=instance.id).exists():
                raise serializers.ValidationError(_("This email is already registered."))
        else:
            if Recruiter.objects.filter(email=value).exists():
                raise serializers.ValidationError(_("This email is already registered."))
        return value

    def create(self, validated_data):
        """Create a new recruiter with profile."""
        from django.db import transaction

        email = validated_data['email']
        password = validated_data['password']
        company = validated_data['company']
        full_name = validated_data['full_name']
        phone_number = validated_data.get('phone_number', '')
        photo = validated_data.get('photo')
        level = validated_data.get('level', RecruiterProfile.Level.RECRUITER)

        with transaction.atomic():
            # Create the Recruiter
            recruiter = Recruiter(
                email=email,
                company=company,
                is_recruiter=True,
                is_active=True,
                is_waiting_approval=False,  # Admin-created recruiters are pre-approved
            )

            # Set password using Django's secure method
            recruiter.set_password(password)
            recruiter.save()

            # Create RecruiterProfile
            RecruiterProfile.objects.create(
                recruiter=recruiter,
                full_name=full_name,
                phone=phone_number,
                photo=photo,
                level=level,
            )

        return recruiter

    def update(self, instance, validated_data):
        """
        Update an existing recruiter and their profile.
        
        Note: The 'company' field is intentionally not updated here.
        Changing a recruiter's company assignment should be done through
        a separate administrative process to ensure proper audit trails
        and permission checks.
        """
        from django.db import transaction

        with transaction.atomic():
            # Update Recruiter fields
            if 'email' in validated_data:
                instance.email = validated_data['email']

            if 'password' in validated_data:
                instance.set_password(validated_data['password'])

            # Note: 'company' field is not updated - company reassignment
            # is not supported through this endpoint for security reasons

            instance.save()

            # Update RecruiterProfile
            try:
                profile = RecruiterProfile.objects.get(recruiter=instance)
            except RecruiterProfile.DoesNotExist:
                # Create profile if it doesn't exist
                profile = RecruiterProfile(recruiter=instance)

            if 'full_name' in validated_data:
                profile.full_name = validated_data['full_name']
            if 'phone_number' in validated_data:
                profile.phone = validated_data['phone_number']
            if 'photo' in validated_data:
                profile.photo = validated_data['photo']
            if 'level' in validated_data:
                profile.level = validated_data['level']

            profile.save()

        return instance

    def to_representation(self, instance):
        """
        Return recruiter data with profile info.
        
        Note: For optimal performance when serializing multiple recruiters,
        ensure the view's queryset uses select_related('recruiterprofile')
        to avoid N+1 queries. Example:
            Recruiter.objects.select_related('recruiterprofile').filter(...)
        """
        # Try to access the profile through the reverse relation
        # This will use the prefetched/selected data if available
        profile = getattr(instance, 'recruiterprofile', None)

        if profile is None:
            # Fallback: try to fetch from DB (for backwards compatibility)
            try:
                profile = RecruiterProfile.objects.get(recruiter=instance)
            except RecruiterProfile.DoesNotExist:
                profile = None

        if profile:
            # Build full URL for photo, return None if empty
            photo_url = None
            if profile.photo and profile.photo.name:
                request = self.context.get("request")
                if request:
                    photo_url = request.build_absolute_uri(profile.photo.url)
                else:
                    photo_url = profile.photo.url

            profile_data = {
                'full_name': profile.full_name,
                'phone_number': profile.phone,
                'photo': photo_url,  # Will be None if no photo
                'level': profile.level,
            }
        else:
            profile_data = {
                'full_name': None,
                'phone_number': None,
                'photo': None,
                'level': None,
            }

        return {
            'id': str(instance.id),
            'email': instance.email,
            'company': str(instance.company_id) if instance.company else None,
            **profile_data,
        }
