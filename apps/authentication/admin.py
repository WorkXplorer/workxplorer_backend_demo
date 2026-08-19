from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from json import JSONDecodeError
from import_export import resources
from import_export.fields import Field
from import_export.admin import ExportActionMixin
from .models import UserConsent, ConsentConfiguration
from .models import CustomUser, Candidate, Recruiter, Company
from .models import MobileSession, RefreshToken, SocialIdentity, OAuthChallenge
from apps.profiles.models import RecruiterProfile
import logging
import requests
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class CandidateResource(resources.ModelResource):
    id = Field(attribute='id', column_name='ID')
    full_name = Field(column_name='Full Name')
    email = Field(attribute='email', column_name='Email')
    phone = Field(column_name='Phone')
    university = Field(attribute='edupartner__name', column_name='University')
    faculty = Field(attribute='faculty__name', column_name='Faculty')
    date_of_birth = Field(attribute='date_of_birth', column_name='Date of Birth')
    is_vault_verified = Field(attribute='is_vault_verified', column_name='Vault Verified')
    is_active = Field(attribute='is_active', column_name='Active')
    date_joined = Field(attribute='date_joined', column_name='Date Joined')

    def dehydrate_full_name(self, candidate):
        profile = getattr(candidate, 'candidateprofile', None)
        return profile.full_name if profile else ''

    def dehydrate_phone(self, candidate):
        profile = getattr(candidate, 'candidateprofile', None)
        return profile.phone if profile else ''

    class Meta:
        model = Candidate
        fields = (
            'id', 'full_name', 'email', 'phone', 'university', 'faculty',
            'date_of_birth', 'is_vault_verified', 'is_active', 'date_joined',
            'onboarding_progress',
        )
        export_order = (
            'id', 'full_name', 'email', 'phone', 'university', 'faculty',
            'date_of_birth', 'is_vault_verified', 'is_active', 'date_joined',
            'onboarding_progress',
        )


class CustomUserAdmin(BaseUserAdmin):
    list_display = ("email", "is_staff", "is_active", "date_joined")
    list_filter = ("is_staff", "is_active", ("date_joined", DateFieldListFilter))
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {"fields": ("last_login", "date_joined")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    search_fields = ("email",)
    ordering = ("email",)


class CandidateInline(admin.TabularInline):
    model = Candidate
    extra = 0
    readonly_fields = ("email", "is_candidate", "is_active", "date_joined")
    can_delete = False
    show_change_link = True
    fields = ("email", "is_candidate", "is_active", "date_joined")

    def has_add_permission(self, request, obj=None):
        return False


class MobileSessionInline(admin.TabularInline):
    """Read-only — shown on a candidate's admin page so support staff can
    see their active app devices without leaving the user record."""
    model = MobileSession
    extra = 0
    can_delete = False
    show_change_link = True
    ordering = ("-created_at",)
    fields = ("device_name", "platform", "auth_method", "status", "created_at", "last_used_at", "idle_expires_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class CandidateAdmin(ExportActionMixin, CustomUserAdmin):
    resource_classes = [CandidateResource]
    model = Candidate
    inlines = [MobileSessionInline]
    list_display = (
        "email",
        "is_candidate",
        "edupartner",
        "faculty",
        "preferred_language",
        "date_joined",
        "is_vault_verified",
    )

    list_filter = (
        "is_candidate",
        "is_active",
        "edupartner",
        "faculty",
        "preferred_language",
        "date_of_birth",
        "is_vault_verified",
        ("date_joined", DateFieldListFilter),
    )

    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Candidate Status",
            {
                "fields": (
                    "is_candidate",
                    "is_active",
                    "edupartner",
                    "faculty",
                    "preferred_language",
                    "date_of_birth",
                    "is_vault_verified",
                    "onboarding_progress",
                )
            },
        ),
        (
            "Important dates",
            {"fields": ("last_login", "date_joined")},
        ),
    )

    readonly_fields = ("is_candidate", "is_active", "date_of_birth", "onboarding_progress")

    def get_queryset(self, request):
        # select_related the FKs and reverse profile so exporting
        # university / phone / full_name doesn't trigger N+1 queries.
        return (
            super()
            .get_queryset(request)
            .select_related("edupartner", "faculty", "candidateprofile")
        )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "edupartner",
                    "faculty",
                    "date_of_birth",
                    "onboarding_progress",      
                ),
            },
        ),
    )


class RecruiterInline(admin.TabularInline):
    model = Recruiter
    extra = 0
    readonly_fields = ("email", "is_recruiter", "is_active", "date_joined")
    can_delete = False
    show_change_link = True
    fields = ("email", "is_recruiter", "is_active", "date_joined")

    def has_add_permission(self, request, obj=None):
        return False


class CompanyAdmin(admin.ModelAdmin):
    model = Company
    list_display = ("name", "domain", "tin", "get_recruiters_count", "is_active", "created_at")
    list_filter = ("domain", "is_active", ("created_at", DateFieldListFilter))
    search_fields = ("name", "tin")
    ordering = ("name",)
    inlines = [RecruiterInline]
    actions = ["activate_inactive_companies"]

    @admin.display(description="Number of Recruiters")
    def get_recruiters_count(self, obj):
        return obj.recruiters.count()

    def _call_company_confirm_api(self, company_ids, is_active):
        """
        Call the CompanyConfirmAPIView endpoint to process company activation/rejection.
        Returns tuple (success: bool, message: str)
        """
        try:
            base_url = getattr(settings, "BACKEND_API_URL", "http://localhost:8000")
            api_url = f"{base_url.rstrip('/')}/api/v1/general/confirm-company/"
            
            payload = {
                "company_ids": [str(cid) for cid in company_ids],
                "is_active": is_active,
            }
            
            response = requests.post(
                api_url,
                json=payload,
                timeout=30,
            )
            
            if response.status_code == 200:
                return True, _("Companies processed successfully. Confirmation emails have been sent.")
            else:
                error_msg = _("No response content")
                if response.content:
                    try:
                        error_msg = response.json().get("message") or response.text.strip()
                    except (JSONDecodeError, ValueError):
                        error_msg = response.text.strip()

                if not error_msg:
                    error_msg = _("HTTP status %(status_code)s") % {
                        "status_code": response.status_code
                    }

                return False, _("API error: %(error)s") % {"error": error_msg}
                
        except requests.exceptions.RequestException as e:
            logging.exception("Failed to call CompanyConfirmAPIView: %s", e)
            return False, _("Failed to connect to API: %(error)s") % {
                "error": str(e)
            }
        except Exception as e:
            logging.exception("Unexpected error calling CompanyConfirmAPIView: %s", e)
            return False, _("Unexpected error: %(error)s") % {"error": str(e)}

    def activate_inactive_companies(self, request, queryset):
        """
        Admin action to activate selected inactive companies.
        Sends a request to CompanyConfirmAPIView API to handle activation and email sending.
        """
        # Filter to only inactive companies
        inactive_companies = queryset.filter(is_active=False)
        
        if not inactive_companies.exists():
            messages.warning(
                request,
                _("No inactive companies selected. All selected companies are already active.")
            )
            return
        
        company_ids = list(inactive_companies.values_list("id", flat=True))
        
        success, message = self._call_company_confirm_api(company_ids, is_active=True)
        
        if success:
            messages.success(
                request,
                message
            )
        else:
            messages.error(
                request,
                message
            )
    
    activate_inactive_companies.short_description = _("✓ Activate selected companies and send confirmation emails")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "domain",
                    "tin",
                    "file",
                    "is_active",
                    "created_at",
                )
            },
        ),
    )

    readonly_fields = ("created_at",)

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "name",
                    "domain",
                    "tin",
                    "file",
                ),
            },
        ),
    )


class RecruiterAdmin(CustomUserAdmin):
    model = Recruiter
    list_display = ("email", "is_recruiter", "company", "is_waiting_approval", "date_joined")

    list_filter = ("is_recruiter", "is_active", "is_waiting_approval", ("date_joined", DateFieldListFilter))

    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "recruiter Status",
            {"fields": ("is_recruiter", "is_active", "company", "is_waiting_approval")},
        ),
        (
            "Important dates",
            {"fields": ("last_login", "date_joined")},
        ),
    )

    readonly_fields = ("is_recruiter", "is_active")

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "company",
                ),
            },
        ),
    )


class RecruiterProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "recruiter", "full_name", "photo", "level")
    list_display_links = ("id", "recruiter", "full_name")
    search_fields = ("recruiter__email", "full_name")
    list_per_page = 25


class UserConsentAdmin(admin.ModelAdmin):
    """View consent records (read-only)"""
    list_display = ('get_consenter', 'consent_type', 'version', 'agreed_at', 'ip_address')
    list_filter = ('consent_type', 'version', 'agreed_at', 'content_type')
    search_fields = ('object_id', 'ip_address')
    ordering = ("-created_at",)
    readonly_fields = (
        'content_type', 'object_id', 'consent_config', 'consent_type', 'version',
        'agreed_at', 'ip_address', 'user_agent', 'withdrawn_at'
    )

    def get_consenter(self, obj):
        """Display who gave consent"""
        if hasattr(obj.consenter, 'email'):
            return f"{obj.consenter.email} ({obj.content_type.model})"
        elif hasattr(obj.consenter, 'name'):
            return f"{obj.consenter.name} (Company)"
        return str(obj.object_id)

    get_consenter.short_description = 'Consenter'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ========================================
# ConsentConfiguration Admin
# ========================================
@admin.register(ConsentConfiguration)
class ConsentConfigurationAdmin(admin.ModelAdmin):
    """
    Manage consent requirements and versions.
    Control what consents are required for candidates, recruiters, and companies.
    """

    list_display = (
        'get_display_name',
        'consent_type',
        'entity_type',
        'version',
        'is_active',
        'created_at',
    )

    list_filter = (
        'entity_type',
        'consent_type',
        'is_active',
        'created_at',
    )

    search_fields = (
        'name',
        'name_uz',
        'name_ru',
        'name_en',
        'description',
    )

    ordering = ('entity_type', 'consent_type', '-created_at')

    fieldsets = (
        ('Configuration', {
            'fields': ('consent_type', 'entity_type', 'version', 'is_active'),
            'description': 'Select which user type this consent applies to and what type of consent it is.'
        }),
        ('Display Names', {
            'fields': ('name', 'name_uz', 'name_ru', 'name_en'),
            'description': 'Provide names in multiple languages. "name" is required as fallback.'
        }),
        ('Descriptions', {
            'fields': ('description', 'description_uz', 'description_ru', 'description_en'),
            'description': 'Provide descriptions in multiple languages (optional).'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ('created_at', 'updated_at')

    def get_display_name(self, obj):
        """Show the name with language indicator if translations exist"""
        has_translations = bool(obj.name_uz or obj.name_ru or obj.name_en)
        suffix = " 🌐" if has_translations else ""
        return f"{obj.name}{suffix}"

    get_display_name.short_description = 'Name'
    get_display_name.admin_order_field = 'name'

    # Bulk actions
    actions = ['activate_consents', 'deactivate_consents', 'duplicate_for_new_version']

    def activate_consents(self, request, queryset):
        """Bulk activate consent configurations"""
        # Check for conflicts before activating
        conflicts = []
        for config in queryset:
            if ConsentConfiguration.objects.filter(
                    consent_type=config.consent_type,
                    entity_type=config.entity_type,
                    is_active=True
            ).exclude(pk=config.pk).exists():
                conflicts.append(f"{config.get_consent_type_display()} for {config.get_entity_type_display()}")

        if conflicts:
            self.message_user(
                request,
                f"Cannot activate - conflicts found: {', '.join(conflicts)}. "
                f"Only one active configuration per consent type + entity type is allowed.",
                level='error'
            )
            return

        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f'{updated} consent configuration(s) activated.'
        )

    activate_consents.short_description = 'Activate selected configurations'

    def deactivate_consents(self, request, queryset):
        """Bulk deactivate consent configurations"""
        # Warn if deactivating configurations with existing records
        records_count = UserConsent.objects.filter(
            consent_config__in=queryset
        ).count()

        updated = queryset.update(is_active=False)

        if records_count > 0:
            self.message_user(
                request,
                f'{updated} configuration(s) deactivated. Note: {records_count} existing consent records '
                f'remain valid and unchanged.',
                level='warning'
            )
        else:
            self.message_user(
                request,
                f'{updated} consent configuration(s) deactivated.'
            )

    deactivate_consents.short_description = 'Deactivate selected configurations'

    def duplicate_for_new_version(self, request, queryset):
        """
        Create duplicates with incremented version for updating policies.
        The duplicates will be inactive - activate them manually after review.
        """
        created = 0
        for config in queryset:
            # Parse and increment version
            try:
                parts = config.version.split('.')
                if len(parts) == 2:
                    major = int(parts[0])
                    minor = int(parts[1])
                    new_version = f"{major}.{minor + 1}"
                else:
                    # For versions like "1" without minor, add .1
                    new_version = f"{config.version}.1"
            except (ValueError, IndexError):
                # If parsing fails, just append "-new"
                new_version = f"{config.version}-new"

            # Check if this version already exists
            if ConsentConfiguration.objects.filter(
                    consent_type=config.consent_type,
                    entity_type=config.entity_type,
                    version=new_version
            ).exists():
                continue

            # Create duplicate with new version (inactive by default)
            ConsentConfiguration.objects.create(
                consent_type=config.consent_type,
                entity_type=config.entity_type,
                version=new_version,
                name=config.name,
                name_uz=config.name_uz,
                name_ru=config.name_ru,
                name_en=config.name_en,
                description=config.description,
                description_uz=config.description_uz,
                description_ru=config.description_ru,
                description_en=config.description_en,
                is_active=False  # Inactive until manually activated
            )
            created += 1

        if created > 0:
            self.message_user(
                request,
                f'Created {created} new version(s) (inactive). Review and activate them to use.',
                level='success'
            )
        else:
            self.message_user(
                request,
                'No new versions created - they may already exist.',
                level='warning'
            )

    duplicate_for_new_version.short_description = 'Duplicate with incremented version (inactive)'

    def save_model(self, request, obj, form, change):
        """
        Override save to show warnings when appropriate.
        """
        if change and not obj.is_active:
            # Deactivating - check for existing records
            record_count = UserConsent.objects.filter(
                consent_type=obj.consent_type,
                version=obj.version
            ).count()

            if record_count > 0:
                self.message_user(
                    request,
                    f"This configuration has {record_count} existing consent records. "
                    f"Deactivating will not delete existing records - they remain valid.",
                    level='warning'
                )

        super().save_model(request, obj, form, change)


# ========================================
# Mobile auth admin — all read-only (view-only permission model, same
# pattern as UserConsentAdmin above). Session data is security-sensitive
# audit trail, not something to hand-edit; the one thing support actually
# needs to *do* is force-revoke a session, exposed as an action instead of
# an editable field.
# ========================================
class RefreshTokenInline(admin.TabularInline):
    """Rotation chain for a session — each row is one refresh, oldest first."""
    model = RefreshToken
    fk_name = "session"
    extra = 0
    can_delete = False
    ordering = ("issued_at",)
    fields = ("token_digest", "parent", "issued_at", "used_at", "expires_at", "revoked_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MobileSession)
class MobileSessionAdmin(admin.ModelAdmin):
    list_display = (
        "get_user_email", "device_name", "platform", "auth_method", "status",
        "created_at", "last_used_at", "idle_expires_at", "absolute_expires_at",
    )
    list_filter = ("status", "platform", "auth_method", ("created_at", DateFieldListFilter))
    search_fields = ("user__email", "device_id", "device_name")
    ordering = ("-created_at",)
    inlines = [RefreshTokenInline]
    actions = ["revoke_selected_sessions"]

    readonly_fields = (
        "id", "user", "device_id", "platform", "app_version", "build_number", "device_name",
        "auth_method", "status", "created_at", "last_used_at", "idle_expires_at",
        "absolute_expires_at", "revoked_at", "revoked_reason",
    )

    @admin.display(description="User", ordering="user__email")
    def get_user_email(self, obj):
        return obj.user.email

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # View-only in the UI; revoking happens through the action below,
        # never by hand-editing status/expiry fields.
        return False

    @admin.action(description="Revoke selected sessions (force logout on that device)")
    def revoke_selected_sessions(self, request, queryset):
        from apps.authentication.services.mobile_session_service import MobileSessionService

        revoked = 0
        for session in queryset.filter(status=MobileSession.Status.ACTIVE):
            MobileSessionService.revoke_session(session, reason="admin_revoked")
            revoked += 1

        if revoked:
            self.message_user(request, f"Revoked {revoked} session(s).", level=messages.SUCCESS)
        else:
            self.message_user(request, "No active sessions in the selection.", level=messages.WARNING)


@admin.register(RefreshToken)
class RefreshTokenAdmin(admin.ModelAdmin):
    """Standalone lookup by digest — useful when incident response has a
    token_digest from a log line and needs to find the session/user it
    belongs to. The raw token itself is never stored, so there's nothing
    sensitive to redact here."""
    list_display = ("token_digest", "get_user_email", "session", "issued_at", "used_at", "expires_at", "revoked_at")
    search_fields = ("token_digest", "session__user__email", "session__device_id")
    list_filter = (("issued_at", DateFieldListFilter),)
    ordering = ("-issued_at",)
    readonly_fields = ("id", "session", "token_digest", "parent", "issued_at", "used_at", "expires_at", "revoked_at")

    @admin.display(description="User", ordering="session__user__email")
    def get_user_email(self, obj):
        return obj.session.user.email

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SocialIdentity)
class SocialIdentityAdmin(admin.ModelAdmin):
    list_display = ("get_user_email", "provider", "subject", "email_at_link", "email_verified", "last_login_at", "created_at")
    list_filter = ("provider", "email_verified", ("created_at", DateFieldListFilter))
    search_fields = ("user__email", "subject", "email_at_link")
    ordering = ("-created_at",)
    readonly_fields = (
        "id", "user", "provider", "subject", "email_at_link", "email_verified",
        "apple_refresh_token_ciphertext", "last_login_at", "created_at", "updated_at",
    )

    @admin.display(description="User", ordering="user__email")
    def get_user_email(self, obj):
        return obj.user.email

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OAuthChallenge)
class OAuthChallengeAdmin(admin.ModelAdmin):
    """Short-lived (5 min TTL) — mainly useful for debugging a failed
    Google/Apple sign-in report ('was a challenge even issued for this
    device?'). Only digests are stored, nothing sensitive to show."""
    list_display = ("provider", "device_id", "created_at", "expires_at", "consumed_at")
    list_filter = ("provider", ("created_at", DateFieldListFilter))
    search_fields = ("device_id",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "provider", "device_id", "nonce_digest", "state_digest", "created_at", "expires_at", "consumed_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# Register all models
admin.site.register(RecruiterProfile, RecruiterProfileAdmin)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Candidate, CandidateAdmin)
admin.site.register(Company, CompanyAdmin)
admin.site.register(Recruiter, RecruiterAdmin)
admin.site.register(UserConsent, UserConsentAdmin)
