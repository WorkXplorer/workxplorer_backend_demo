from django.contrib import admin
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
    CandidateSubscription,
    SubscriptionSeatAssignment,
    CompanyFeatureUsage,
)


@admin.register(CompanyFeatureUsage)
class CompanyFeatureUsageAdmin(admin.ModelAdmin):
    list_display = ["company", "feature", "usage_month", "usage_count"]
    list_filter = ["feature", "usage_month"]
    search_fields = ["company__name"]
    raw_id_fields = ["company", "feature"]
    readonly_fields = ["created_at", "updated_at"]


class PlanFeatureInline(admin.TabularInline):
    model = PlanFeature
    extra = 1
    autocomplete_fields = ["feature"]


class SeatAssignmentInline(admin.TabularInline):
    model = SubscriptionSeatAssignment
    extra = 0
    readonly_fields = ["created_at"]
    autocomplete_fields = ["recruiter"]


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "plan_type",
        "max_admins",
        "max_recruiters",
        "price",
        "is_active",
        "display_order",
    ]
    list_filter = ["plan_type", "is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PlanFeatureInline]
    ordering = ["display_order"]


@admin.register(SubscriptionFeature)
class SubscriptionFeatureAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "feature_type", "is_active"]
    list_filter = ["feature_type", "is_active"]
    search_fields = ["name", "code"]


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "company",
        "plan",
        "status",
        "has_design",
        "starts_at",
        "expires_at",
        "created_at",
    ]
    list_filter = ["status", "plan", "has_design"]
    search_fields = ["company__name"]
    autocomplete_fields = ["company", "plan"]
    inlines = [SeatAssignmentInline]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CandidateSubscription)
class CandidateSubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "candidate",
        "plan",
        "status",
        "starts_at",
        "expires_at",
        "created_at",
    ]
    list_filter = ["status", "plan"]
    search_fields = ["candidate__email"]
    autocomplete_fields = ["candidate", "plan"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(SubscriptionSeatAssignment)
class SubscriptionSeatAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        "recruiter",
        "subscription",
        "seat_type",
        "is_active",
        "created_at",
    ]
    list_filter = ["seat_type", "is_active"]
    search_fields = ["recruiter__email"]
    autocomplete_fields = ["subscription", "recruiter"]
    readonly_fields = ["created_at", "updated_at"]
