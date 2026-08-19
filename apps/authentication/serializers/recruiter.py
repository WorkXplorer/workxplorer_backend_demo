from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _

from ..models.recruiter import Company, Recruiter
from apps.domain.models import Domain
from apps.profiles.models import CompanyProfile, RecruiterProfile
from ..services.consent_service import ConsentService
from utils import validate_uploaded_file


class CompanyRegistrationSerializer(serializers.Serializer):
    company_email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
    domain_id = serializers.PrimaryKeyRelatedField(
        queryset=Domain.objects.all(),
        required=False,
        allow_null=True,
        help_text="Company specialization domain"
    )
    inn = serializers.CharField(max_length=9)
    phone_number = serializers.CharField(max_length=20, required=True)
    file = serializers.FileField(required=False, allow_null=True)
    website = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    recruiter_emails = serializers.JSONField(required=False, default=list)

    # Single boolean for company consent agreement
    company_agreed_to_all_consents = serializers.BooleanField(
        write_only=True,
        required=True,
        help_text="Company must agree to all required policies"
    )

    # Single boolean for admin recruiter consent agreement
    admin_agreed_to_all_consents = serializers.BooleanField(
        write_only=True,
        required=True,
        help_text="Admin recruiter must agree to all required policies"
    )

    def validate_inn(self, value):
        """Check if TIN already exists and if it has a valid length"""
        if Company.objects.filter(tin=value).exists() or len(value) != 9:
            raise serializers.ValidationError(_("Company with this TIN already exists or TIN length is invalid."))
        return value

    def validate_file(self, value):
        if value is None:
            return value

        validate_uploaded_file(value)

        file_extension_validator = FileExtensionValidator(
            allowed_extensions=["pdf", "doc", "docx", "zip"],
            message=_("Invalid file format. Only PDF, DOC, DOCX, and ZIP files are allowed."),
        )
        try:
            file_extension_validator(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))

        if hasattr(value, "size") and value.size > settings.MAX_FILE_SIZE:
            raise serializers.ValidationError(
                _("File size should not exceed %(limit)sMB")
                % {"limit": settings.MAX_FILE_SIZE // (1024 * 1024)}
            )

        return value

    def validate_company_email(self, value):
        """Normalize admin email. Uniqueness is enforced at create time."""
        normalized_email = value.lower().strip()
        return normalized_email

    def validate_recruiter_emails(self, value):
        """Validate recruiter emails with case-insensitive uniqueness check and subscription limits."""
        if not isinstance(value, list):
            raise serializers.ValidationError(_("recruiter_emails must be a list."))

        # --- Check subscription recruiter limits ---
        from apps.subscriptions.services import SubscriptionService

        # Count admins and recruiters in the incoming list
        admin_count = 0
        recruiter_count = 0
        for item in value:
            level = item.get("level", "Recruiter") if isinstance(item, dict) else "Recruiter"
            if str(level).lower() == "admin":
                admin_count += 1
            else:
                recruiter_count += 1

        # The main company_email is always an admin (+1)
        total_admins = 1 + admin_count
        total_recruiters = recruiter_count

        limit_check = SubscriptionService.check_recruiter_limit(
            company=None,  # New company — uses free plan stored in DB
            num_admins=total_admins,
            num_recruiters=total_recruiters,
            plan_override=self.context.get("company_free_plan"),
        )
        if not limit_check["allowed"]:
            # Return structured list of error messages for easier API consumption
            raise serializers.ValidationError(limit_check.get("errors", []))

        normalized_emails = []
        result = []
        for item in value:
            if not isinstance(item, dict) or "email" not in item:
                raise serializers.ValidationError(
                    _("Each item must be an object with 'email' field.")
                )
            email = item["email"]

            # Validate email format
            email_validator = serializers.EmailField()
            try:
                email = email_validator.run_validation(email)
            except serializers.ValidationError:
                raise serializers.ValidationError("Invalid email format: {email}").format(email=email)

            normalized_email = email.lower().strip()
            normalized_emails.append(normalized_email)

            # Consent is NOT required at registration time for additional recruiters.
            # They will be asked to agree to policies when they receive the
            # set-password link after the company is approved.

            result.append({
                "email": normalized_email,
                "level": item.get("level", "Recruiter"),
            })

        # Check for duplicates
        if len(normalized_emails) != len(set(normalized_emails)):
            raise serializers.ValidationError(_("Duplicate emails in recruiter list."))

        # Check if any email already exists — report each taken email individually
        if normalized_emails:
            from django.db.models import Q
            email_query = Q()
            for email in normalized_emails:
                email_query |= Q(email__iexact=email)

            existing_set = set(
                Recruiter.objects.filter(email_query).values_list("email", flat=True)
            )
            if existing_set:
                errors = [
                    _("'%(email)s' is already taken. Please use a different email.") % {"email": email}
                    for email in normalized_emails
                    if email.lower() in {e.lower() for e in existing_set}
                ]
                raise serializers.ValidationError(errors)

        return result

    def validate_company_agreed_to_all_consents(self, value):
        """Validate company consents exist"""
        if not value:
            raise serializers.ValidationError(
                "Company must agree to all required policies to register"
            )

        request = self.context.get("request")
        is_valid, error_msg, _ = ConsentService.validate_entity_type(
            'company',
            request=request,
        )
        if not is_valid:
            raise serializers.ValidationError(error_msg)

        return value

    def validate_admin_agreed_to_all_consents(self, value):
        """Validate admin recruiter consents exist"""
        if not value:
            raise serializers.ValidationError(
                "Admin recruiter must agree to all required policies to register"
            )

        request = self.context.get("request")
        is_valid, error_msg, _ = ConsentService.validate_entity_type(
            'recruiter',
            request=request,
        )
        if not is_valid:
            raise serializers.ValidationError(error_msg)

        return value


class RecruiterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=Recruiter.objects.all(), message="This email already exists"
            )
        ],
    )
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=True
    )
    full_name = serializers.CharField(max_length=255, required=True, write_only=True)
    profile_full_name = serializers.SerializerMethodField(read_only=True)
    is_recruiter = serializers.BooleanField(read_only=True)

    # Single boolean for consent agreement
    agreed_to_all_consents = serializers.BooleanField(
        write_only=True,
        required=True,
        help_text="Must agree to all required policies"
    )

    class Meta:
        model = Recruiter
        fields = ("id", "email", "is_recruiter", "company", "full_name",
                  "profile_full_name", "agreed_to_all_consents")

    def get_profile_full_name(self, obj):
        """Get full name from related RecruiterProfile"""
        try:
            profile = RecruiterProfile.objects.get(recruiter=obj)
            return profile.full_name
        except RecruiterProfile.DoesNotExist:
            return None

    def validate_agreed_to_all_consents(self, value):
        """Validate recruiter consents"""
        if not value:
            raise serializers.ValidationError(
                "You must agree to all required policies to register"
            )

        is_valid, error_msg, _ = ConsentService.validate_entity_type('recruiter')
        if not is_valid:
            raise serializers.ValidationError(error_msg)

        return value

    def validate_company(self, company):
        """Block self-registration for unapproved companies."""
        if not company.is_active:
            raise serializers.ValidationError(
                _("This company has not been approved yet. Recruiter registration is unavailable.")
            )
        return company

    def create(self, validated_data):
        agreed_to_all_consents = validated_data.pop("agreed_to_all_consents", False)
        full_name = validated_data.pop("full_name", None)

        if not full_name:
            raise serializers.ValidationError({"full_name": "Full name is required."})

        # Create the recruiter user
        user = Recruiter(
            email=validated_data["email"],
            company=validated_data["company"],
            is_recruiter=True,
            is_active=True,
            is_waiting_approval=True,
        )

        user.set_unusable_password()
        user.save()

        # Create RecruiterProfile
        RecruiterProfile.objects.create(
            recruiter=user,
            full_name=full_name,
        )

        # Create consent records if user agreed
        if agreed_to_all_consents:
            request = self.context.get('request')
            ip_address = ConsentService.get_client_ip(request)
            user_agent = request.headers.get('User-Agent', '') if request else ''

            ConsentService.create_consents_for_entity(
                consenter=user,
                entity_type='recruiter',
                ip_address=ip_address,
                user_agent=user_agent,
                request=request,
            )

        return user


# Keep existing CompanySerializer and CompanyProfileSerializer unchanged
class CompanySerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField(read_only=True)
    phone_number = serializers.SerializerMethodField(read_only=True)
    company_photo = serializers.SerializerMethodField(read_only=True)
    date = serializers.SerializerMethodField(read_only=True)
    description = serializers.SerializerMethodField(read_only=True)
    address = serializers.SerializerMethodField(read_only=True)
    domain = serializers.CharField(source='domain.name', read_only=True)

    class Meta:
        model = Company
        fields = ("id", "name", "is_active", "domain", "company_photo",
                  "email", "phone_number", "date", "description", "address")

    def get_company_profile(self, obj):
        if hasattr(obj, 'company_profiles'):
            return obj.company_profiles[0] if obj.company_profiles else None
        if not hasattr(obj, '_company_profile_cache'):
            try:
                obj._company_profile_cache = obj.companyprofile_set.first()
            except Exception:
                obj._company_profile_cache = None
        return obj._company_profile_cache

    def get_company_photo(self, obj):
        profile = self.get_company_profile(obj)
        if profile and profile.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(profile.photo.url)
            return profile.photo.url
        return None

    def get_date(self, obj):
        profile = self.get_company_profile(obj)
        return profile.created_at if profile else None

    def get_address(self, obj):
        profile = self.get_company_profile(obj)
        return profile.address if profile else None

    def get_description(self, obj):
        profile = self.get_company_profile(obj)
        return profile.description if profile else None

    def get_email(self, obj):
        if hasattr(obj, 'all_recruiters'):
            first_recruiter = obj.all_recruiters[0] if obj.all_recruiters else None
            return first_recruiter.email if first_recruiter else None
        if not hasattr(obj, '_first_recruiter_cache'):
            obj._first_recruiter_cache = obj.recruiters.order_by('date_joined').first()
        first_recruiter = obj._first_recruiter_cache
        return first_recruiter.email if first_recruiter else None

    def get_phone_number(self, obj):
        if hasattr(obj, 'all_recruiters'):
            first_recruiter = obj.all_recruiters[0] if obj.all_recruiters else None
            if first_recruiter:
                profile = first_recruiter.recruiterprofile_set.first() if hasattr(first_recruiter,
                                                                                  'recruiterprofile_set') else None
                return profile.phone if profile else None
            return None
        if not hasattr(obj, '_first_recruiter_cache'):
            obj._first_recruiter_cache = obj.recruiters.order_by('date_joined').first()
        first_recruiter = obj._first_recruiter_cache
        if first_recruiter:
            profile = first_recruiter.recruiterprofile_set.first()
            return profile.phone if profile else None
        return None


class CompanyProfileSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(read_only=True)
    photo = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["jpg", "jpeg", "png"],
                message=_("Invalid file format. Only JPG, JPEG, and PNG images are allowed."),
            )
        ],
        error_messages={
            "invalid": _("Invalid file format. Only JPG, JPEG, and PNG images are allowed."),
            "invalid_image": _("Invalid file format. Only JPG, JPEG, and PNG images are allowed."),
        },
    )

    def validate_photo(self, value):
        if value is None:
            return value

        validate_uploaded_file(value)

        if hasattr(value, "size") and value.size > settings.MAX_FILE_SIZE:
            raise serializers.ValidationError(
                _("Photo size should not exceed %(limit)sMB")
                % {"limit": settings.MAX_FILE_SIZE // (1024 * 1024)}
            )

        return value

    class Meta:
        model = CompanyProfile
        fields = ("id", "company", "photo", "description", "address", "website", "phone_number")
        extra_kwargs = {
            "photo": {"required": False, "allow_null": True},
            "description": {"required": False, "allow_blank": True},
            "address": {"required": False, "allow_blank": True},
            "website": {"required": False, "allow_blank": True},
            "phone_number": {"required": False, "allow_blank": True},
        }
