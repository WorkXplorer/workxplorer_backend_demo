"""
Management command to seed initial subscription plans and features.

Run this after migrations to set up the default subscription data:

    python manage.py seed_subscriptions

This command is idempotent — it will skip records that already exist
(matched by slug for plans and code for features).

Plans created:
    Company: free, basic, pro
    Candidate: free

Features created:
    Company: company_analytics, full_analytics, headhunting_access,
             vacancy_limit, template_limit
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
)
from apps.subscriptions.services import (
    COMPANY_FREE_PLAN_SLUG,
    COMPANY_BASIC_PLAN_SLUG,
    COMPANY_PRO_PLAN_SLUG,
    CANDIDATE_FREE_PLAN_SLUG,
    CANDIDATE_BASIC_PLAN_SLUG,
    CANDIDATE_PRO_PLAN_SLUG,
    FEATURE_COMPANY_ANALYTICS,
    FEATURE_FULL_ANALYTICS,
    FEATURE_HEADHUNTING_ACCESS,
    FEATURE_VACANCY_LIMIT,
    FEATURE_TEMPLATE_LIMIT,
    FEATURE_AI_RESUME_GENERATION,
    FEATURE_ANALYTICS_REGENERATION,
    FEATURE_AI_TEMPLATE_GENERATION,
    DEFAULT_VACANCY_LIMITS,
    DEFAULT_TEMPLATE_LIMITS,
    DEFAULT_AI_GENERATION_LIMITS,
    DEFAULT_ANALYTICS_REGENERATION_LIMITS,
)


# ──────────────────────────────────────────────────────────
# Plan definitions
# ──────────────────────────────────────────────────────────

PLANS = [
    {
        "slug": COMPANY_FREE_PLAN_SLUG,
        "name": "Free",
        "plan_type": "company",
        "description": "Basic plan with no analytics. 1 admin, 3 recruiters.",
        "max_admins": 1,
        "max_recruiters": 3,
        "price": 0,
        "display_order": 1,
    },
    {
        "slug": COMPANY_BASIC_PLAN_SLUG,
        "name": "Basic",
        "plan_type": "company",
        "description": (
            "Company analytics included. 2 admins, 5 recruiters. "
            "Access to unresponded candidates."
        ),
        "max_admins": 2,
        "max_recruiters": 5,
        "price": 0,  # Price TBD — set to 0 until payment is integrated
        "display_order": 2,
    },
    {
        "slug": COMPANY_PRO_PLAN_SLUG,
        "name": "Pro",
        "plan_type": "company",
        "description": (
            "Full analytics included. 3 admins, 10 recruiters. "
            "Access to unresponded candidates."
        ),
        "max_admins": 3,
        "max_recruiters": 10,
        "price": 0,  # Price TBD
        "display_order": 3,
    },
    {
        "slug": CANDIDATE_FREE_PLAN_SLUG,
        "name": "Free",
        "plan_type": "candidate",
        "description": "1 AI resume generation per month.",
        "max_admins": 0,
        "max_recruiters": 0,
        "price": 0,
        "display_order": 1,
    },
    {
        "slug": CANDIDATE_BASIC_PLAN_SLUG,
        "name": "Basic",
        "plan_type": "candidate",
        "description": "10 AI resume generations per month.",
        "max_admins": 0,
        "max_recruiters": 0,
        "price": 0,
        "display_order": 2,
    },
    {
        "slug": CANDIDATE_PRO_PLAN_SLUG,
        "name": "Pro",
        "plan_type": "candidate",
        "description": "30 AI resume generations per month.",
        "max_admins": 0,
        "max_recruiters": 0,
        "price": 0,
        "display_order": 3,
    },
]

# ──────────────────────────────────────────────────────────
# Feature definitions
# ──────────────────────────────────────────────────────────

FEATURES = [
    {
        "code": FEATURE_COMPANY_ANALYTICS,
        "name": "Company Analytics",
        "description": "Access to company-level analytics dashboard.",
        "feature_type": "company",
    },
    {
        "code": FEATURE_FULL_ANALYTICS,
        "name": "Full Analytics",
        "description": "Access to full/advanced analytics with detailed insights.",
        "feature_type": "company",
    },
    {
        "code": FEATURE_HEADHUNTING_ACCESS,
        "name": "Headhunting Access",
        "description": (
            "Ability to contact unresponded candidates — "
            "send offers and invitations to candidates who haven't applied."
        ),
        "feature_type": "company",
    },
    {
        "code": FEATURE_VACANCY_LIMIT,
        "name": "Vacancy Limit",
        "description": (
            "Controls the maximum number of active vacancies and "
            "the maximum expiration period for vacancies."
        ),
        "feature_type": "company",
    },
    {
        "code": FEATURE_TEMPLATE_LIMIT,
        "name": "Template Limit",
        "description": (
            "Controls the maximum number of status change templates "
            "a company can create."
        ),
        "feature_type": "company",
    },
    {
        "code": FEATURE_AI_TEMPLATE_GENERATION,
        "name": "AI Template Generation",
        "description": (
            "Allows AI-powered drafting of HR message templates "
            "(invitation / interview / rejection)."
        ),
        "feature_type": "company",
    },
    {
        "code": FEATURE_AI_RESUME_GENERATION,
        "name": "AI Resume Generation",
        "description": (
            "Allows AI-powered resume generation. "
            "Usage is limited per month based on the plan configuration."
        ),
        "feature_type": "candidate",
    },
    {
        "code": FEATURE_ANALYTICS_REGENERATION,
        "name": "Analytics Regeneration",
        "description": (
            "Allows regeneration of student analytics "
            "(dashboard and roadmap). "
            "Usage is limited per month based on the plan configuration."
        ),
        "feature_type": "candidate",
    },
]

# ──────────────────────────────────────────────────────────
# Plan → Feature mapping
# Which features are enabled for each plan
# ──────────────────────────────────────────────────────────

PLAN_FEATURES = {
    # Free: no analytics, no headhunting; vacancy + reason limits apply
    COMPANY_FREE_PLAN_SLUG: [
        {
            "code": FEATURE_VACANCY_LIMIT,
            "configuration": DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG],
        },
        {
            "code": FEATURE_TEMPLATE_LIMIT,
            "configuration": DEFAULT_TEMPLATE_LIMITS[COMPANY_FREE_PLAN_SLUG],
        },
    ],
    # Basic: company analytics + headhunting + higher limits
    COMPANY_BASIC_PLAN_SLUG: [
        {"code": FEATURE_COMPANY_ANALYTICS},
        {"code": FEATURE_HEADHUNTING_ACCESS},
        {
            "code": FEATURE_VACANCY_LIMIT,
            "configuration": DEFAULT_VACANCY_LIMITS[COMPANY_BASIC_PLAN_SLUG],
        },
        {
            "code": FEATURE_TEMPLATE_LIMIT,
            "configuration": DEFAULT_TEMPLATE_LIMITS[COMPANY_BASIC_PLAN_SLUG],
        },
    ],
    # Pro: full analytics + headhunting + AI template drafting + highest limits
    COMPANY_PRO_PLAN_SLUG: [
        {"code": FEATURE_COMPANY_ANALYTICS},
        {"code": FEATURE_FULL_ANALYTICS},
        {"code": FEATURE_HEADHUNTING_ACCESS},
        {"code": FEATURE_AI_TEMPLATE_GENERATION},
        {
            "code": FEATURE_VACANCY_LIMIT,
            "configuration": DEFAULT_VACANCY_LIMITS[COMPANY_PRO_PLAN_SLUG],
        },
        {
            "code": FEATURE_TEMPLATE_LIMIT,
            "configuration": DEFAULT_TEMPLATE_LIMITS[COMPANY_PRO_PLAN_SLUG],
        },
    ],
    # Candidate free: AI resume generation (1/month) + analytics regeneration (30/month)
    CANDIDATE_FREE_PLAN_SLUG: [
        {
            "code": FEATURE_AI_RESUME_GENERATION,
            "configuration": DEFAULT_AI_GENERATION_LIMITS[CANDIDATE_FREE_PLAN_SLUG],
        },
        {
            "code": FEATURE_ANALYTICS_REGENERATION,
            "configuration": DEFAULT_ANALYTICS_REGENERATION_LIMITS[CANDIDATE_FREE_PLAN_SLUG],
        },
    ],
    # Candidate basic: AI resume generation (10/month) + analytics regeneration (50/month)
    CANDIDATE_BASIC_PLAN_SLUG: [
        {
            "code": FEATURE_AI_RESUME_GENERATION,
            "configuration": DEFAULT_AI_GENERATION_LIMITS[CANDIDATE_BASIC_PLAN_SLUG],
        },
        {
            "code": FEATURE_ANALYTICS_REGENERATION,
            "configuration": DEFAULT_ANALYTICS_REGENERATION_LIMITS[CANDIDATE_BASIC_PLAN_SLUG],
        },
    ],
    # Candidate pro: AI resume generation (30/month) + analytics regeneration (100/month)
    CANDIDATE_PRO_PLAN_SLUG: [
        {
            "code": FEATURE_AI_RESUME_GENERATION,
            "configuration": DEFAULT_AI_GENERATION_LIMITS[CANDIDATE_PRO_PLAN_SLUG],
        },
        {
            "code": FEATURE_ANALYTICS_REGENERATION,
            "configuration": DEFAULT_ANALYTICS_REGENERATION_LIMITS[CANDIDATE_PRO_PLAN_SLUG],
        },
    ],
}


class Command(BaseCommand):
    help = "Seed initial subscription plans, features, and plan-feature links."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing records with latest values instead of skipping them.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        update = options["update"]
        self.stdout.write("Seeding subscription data...\n")
        if update:
            self.stdout.write(
                self.style.WARNING("  --update flag set: existing records will be updated.\n")
            )

        # 1. Create features
        features_map = {}
        for feature_data in FEATURES:
            defaults = {
                "name": feature_data["name"],
                "description": feature_data["description"],
                "feature_type": feature_data["feature_type"],
            }
            if update:
                feature, created = SubscriptionFeature.objects.update_or_create(
                    code=feature_data["code"],
                    defaults=defaults,
                )
                status_label = "CREATED" if created else "UPDATED"
            else:
                feature, created = SubscriptionFeature.objects.get_or_create(
                    code=feature_data["code"],
                    defaults=defaults,
                )
                status_label = "CREATED" if created else "EXISTS"
            features_map[feature.code] = feature
            self.stdout.write(f"  Feature: {feature.name} [{status_label}]")

        # 2. Create plans
        plans_map = {}
        for plan_data in PLANS:
            defaults = {
                "name": plan_data["name"],
                "plan_type": plan_data["plan_type"],
                "description": plan_data["description"],
                "max_admins": plan_data["max_admins"],
                "max_recruiters": plan_data["max_recruiters"],
                "price": plan_data["price"],
                "display_order": plan_data["display_order"],
            }
            if update:
                plan, created = SubscriptionPlan.objects.update_or_create(
                    slug=plan_data["slug"],
                    defaults=defaults,
                )
                status_label = "CREATED" if created else "UPDATED"
            else:
                plan, created = SubscriptionPlan.objects.get_or_create(
                    slug=plan_data["slug"],
                    defaults=defaults,
                )
                status_label = "CREATED" if created else "EXISTS"
            plans_map[plan.slug] = plan
            self.stdout.write(f"  Plan: {plan.name} ({plan.plan_type}) [{status_label}]")

        # 3. Create plan-feature links
        for plan_slug, feature_entries in PLAN_FEATURES.items():
            plan = plans_map.get(plan_slug)
            if not plan:
                continue
            for entry in feature_entries:
                # Support both old string format and new dict format
                if isinstance(entry, str):
                    feature_code = entry
                    configuration = {}
                else:
                    feature_code = entry["code"]
                    configuration = entry.get("configuration", {})

                feature = features_map.get(feature_code)
                if not feature:
                    continue

                if update:
                    pf, created = PlanFeature.objects.update_or_create(
                        plan=plan,
                        feature=feature,
                        defaults={
                            "is_enabled": True,
                            "configuration": configuration,
                        },
                    )
                    status_label = "CREATED" if created else "UPDATED"
                else:
                    pf, created = PlanFeature.objects.get_or_create(
                        plan=plan,
                        feature=feature,
                        defaults={
                            "is_enabled": True,
                            "configuration": configuration,
                        },
                    )
                    status_label = "CREATED" if created else "EXISTS"

                config_info = f" config={configuration}" if configuration else ""
                self.stdout.write(
                    f"  PlanFeature: {plan.name} → {feature.name} [{status_label}]{config_info}"
                )

        self.stdout.write(
            self.style.SUCCESS("\nSubscription data seeded successfully!")
        )
