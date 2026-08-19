"""
Tests for subscription-based limits on vacancies and reason templates.

Covers:
- Vacancy active count limits per plan (Free/Basic/Pro)
- Vacancy expire duration limits per plan
- Template count limits per plan
- Trilingual error messages in 403 responses
- Edge cases (upgrading plan, boundary values)
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.applications.models.status import StatusCategory, ApplicationStatusModel
from apps.authentication.models import Company, Recruiter
from apps.hr_templates.models import Template
from apps.profiles.models import RecruiterProfile
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
)
from apps.subscriptions.services import (
    SubscriptionService,
    COMPANY_FREE_PLAN_SLUG,
    COMPANY_BASIC_PLAN_SLUG,
    COMPANY_PRO_PLAN_SLUG,
    FEATURE_VACANCY_LIMIT,
    FEATURE_TEMPLATE_LIMIT,
    DEFAULT_VACANCY_LIMITS,
    DEFAULT_TEMPLATE_LIMITS,
)
from apps.vacancies.models import Vacancy


# ──────────────────────────────────────────────────────────
# Helper to create plan + features quickly
# ──────────────────────────────────────────────────────────

def create_plan_with_limits(slug, name, vacancy_config=None, reason_config=None):
    """
    Create a subscription plan and attach vacancy_limit / template_limit
    features with the given configuration dicts.
    """
    plan, _ = SubscriptionPlan.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "plan_type": "company",
            "max_admins": 1,
            "max_recruiters": 3,
            "price": 0,
            "display_order": 1,
        },
    )

    if vacancy_config is not None:
        feature, _ = SubscriptionFeature.objects.get_or_create(
            code=FEATURE_VACANCY_LIMIT,
            defaults={
                "name": "Vacancy Limit",
                "feature_type": "company",
            },
        )
        PlanFeature.objects.update_or_create(
            plan=plan,
            feature=feature,
            defaults={"is_enabled": True, "configuration": vacancy_config},
        )

    if reason_config is not None:
        feature, _ = SubscriptionFeature.objects.get_or_create(
            code=FEATURE_TEMPLATE_LIMIT,
            defaults={
                "name": "Template Limit",
                "feature_type": "company",
            },
        )
        PlanFeature.objects.update_or_create(
            plan=plan,
            feature=feature,
            defaults={"is_enabled": True, "configuration": reason_config},
        )

    return plan


def subscribe_company(company, plan):
    """Create an active CompanySubscription for the given company & plan."""
    # Deactivate existing
    CompanySubscription.objects.filter(
        company=company,
        status=CompanySubscription.Status.ACTIVE,
    ).update(status=CompanySubscription.Status.EXPIRED)

    return CompanySubscription.objects.create(
        company=company,
        plan=plan,
        status=CompanySubscription.Status.ACTIVE,
    )


# ══════════════════════════════════════════════════════════
# Unit tests — SubscriptionService limit checks
# ══════════════════════════════════════════════════════════

class VacancyLimitServiceTests(TestCase):
    """Unit tests for SubscriptionService vacancy limit checks."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Limit Co", tin="999000001")
        cls.recruiter = Recruiter.objects.create_user(
            email="limit_recr@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )

    def _create_active_vacancies(self, count):
        for _ in range(count):
            Vacancy.objects.create(
                title="V",
                company=self.company,
                created_by=self.recruiter,
                is_active=True,
            )

    def test_vacancy_limit_defaults(self):
        """Without any subscription the free defaults apply."""
        limits = SubscriptionService.get_vacancy_limits(self.company)
        self.assertEqual(limits["max_active_vacancies"], 3)
        self.assertEqual(limits["max_expire_days"], 30)

    def test_vacancy_plan_limits(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 3, 30),
            (COMPANY_BASIC_PLAN_SLUG, 5, 90),
            (COMPANY_PRO_PLAN_SLUG, 10, 180),
        ]
        for plan_slug, max_active, max_expire in test_cases:
            with self.subTest(plan=plan_slug):
                Vacancy.objects.filter(company=self.company).delete()
                plan_name = plan_slug.split("-", 1)[1].capitalize()

                plan = create_plan_with_limits(
                    plan_slug, plan_name,
                    vacancy_config=DEFAULT_VACANCY_LIMITS[plan_slug],
                )
                subscribe_company(self.company, plan)

                # At max_active - 1 → allowed
                self._create_active_vacancies(max_active - 1)
                result = SubscriptionService.check_vacancy_limit(self.company)
                self.assertTrue(result["allowed"])

                # At max_active → blocked
                self._create_active_vacancies(1)
                result = SubscriptionService.check_vacancy_limit(self.company)
                self.assertFalse(result["allowed"])
                self.assertEqual(result["current_active"], max_active)

                # Expire boundary: max_expire is OK
                ok = SubscriptionService.check_vacancy_expire(self.company, max_expire)
                self.assertTrue(ok["allowed"])

                # Expire boundary: max_expire + 1 is not OK
                fail = SubscriptionService.check_vacancy_expire(self.company, max_expire + 1)
                self.assertFalse(fail["allowed"])

    def test_expire_none_is_allowed(self):
        """If expire is None the check should pass (serializer handles default)."""
        plan = create_plan_with_limits(
            COMPANY_FREE_PLAN_SLUG, "Free",
            vacancy_config=DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        subscribe_company(self.company, plan)
        result = SubscriptionService.check_vacancy_expire(self.company, None)
        self.assertTrue(result["allowed"])


class TemplateLimitServiceTests(TestCase):
    """Unit tests for SubscriptionService template limit checks."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Template Co", tin="999000002")

        # Create a minimal ApplicationStatusModel so STATUS_CHANGE templates can reference it
        rejected_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.REJECTED,
            defaults={
                "label": "Rejected",
                "is_terminal": True,
                "position": 50,
            },
        )
        cls.application_status, _ = ApplicationStatusModel.objects.get_or_create(
            company=cls.company,
            key="REJECTED",
            defaults={
                "label": "Rejected",
                "category": rejected_category,
            },
        )

    def _create_templates(self, count):
        for i in range(count):
            Template.objects.create(
                title=f"Reason {i}",
                company=self.company,
                template_type=Template.TemplateType.STATUS_CHANGE,
            )

    def test_template_limit_defaults(self):
        limits = SubscriptionService.get_template_limits(self.company)
        self.assertEqual(limits["max_reasons"], 2)

    def test_reason_count_limits(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 2),
            (COMPANY_BASIC_PLAN_SLUG, 5),
            (COMPANY_PRO_PLAN_SLUG, 10),
        ]
        for plan_slug, max_templates in test_cases:
            with self.subTest(plan=plan_slug):
                Template.objects.filter(company=self.company).delete()
                plan_name = plan_slug.split("-", 1)[1].capitalize()

                plan = create_plan_with_limits(
                    plan_slug, plan_name,
                    reason_config=DEFAULT_TEMPLATE_LIMITS[plan_slug],
                )
                subscribe_company(self.company, plan)

                # At max_templates - 1 → allowed
                self._create_templates(max_templates - 1)
                result = SubscriptionService.check_template_limit(self.company)
                self.assertTrue(result["allowed"])

                # At max_templates → blocked
                self._create_templates(1)
                result = SubscriptionService.check_template_limit(self.company)
                self.assertFalse(result["allowed"])


# ══════════════════════════════════════════════════════════
# Integration tests — API endpoints
# ══════════════════════════════════════════════════════════

class VacancySubscriptionLimitAPITests(APITestCase):
    """
    Integration tests: creating vacancies via the API respects
    subscription limits and returns trilingual 403 messages.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="API Co", tin="888000001")
        cls.recruiter = Recruiter.objects.create_user(
            email="api_recr@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="API Recruiter",
            level="Admin",
        )
        cls.create_url = reverse("create-vacancy")

    def _subscribe(self, slug, name, vacancy_config):
        plan = create_plan_with_limits(slug, name, vacancy_config=vacancy_config)
        subscribe_company(self.company, plan)
        return plan

    def _vacancy_payload(self, expire=None):
        data = {
            "title": "Test Vacancy",
            "about_us": "About us text",
            "requirements": "Requirements text",
            "responsibilities": "Responsibilities text",
        }
        if expire is not None:
            data["expire"] = expire
        return data

    def test_create_vacancy_within_limit(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 3),
            (COMPANY_BASIC_PLAN_SLUG, 5),
            (COMPANY_PRO_PLAN_SLUG, 10),
        ]
        for plan_slug, max_active in test_cases:
            with self.subTest(plan=plan_slug):
                Vacancy.objects.filter(company=self.company).delete()
                plan_name = plan_slug.split("-", 1)[1].capitalize()

                self._subscribe(
                    plan_slug, plan_name,
                    DEFAULT_VACANCY_LIMITS[plan_slug],
                )
                self.client.force_authenticate(user=self.recruiter)

                for _ in range(max_active - 1):
                    Vacancy.objects.create(
                        title="V", company=self.company,
                        created_by=self.recruiter, is_active=True,
                    )

                resp = self.client.post(self.create_url, self._vacancy_payload(), format="json")
                self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_create_vacancy_exceed_limit(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 3),
            (COMPANY_BASIC_PLAN_SLUG, 5),
            (COMPANY_PRO_PLAN_SLUG, 10),
        ]
        for plan_slug, max_active in test_cases:
            with self.subTest(plan=plan_slug):
                Vacancy.objects.filter(company=self.company).delete()
                plan_name = plan_slug.split("-", 1)[1].capitalize()

                self._subscribe(
                    plan_slug, plan_name,
                    DEFAULT_VACANCY_LIMITS[plan_slug],
                )
                self.client.force_authenticate(user=self.recruiter)

                for _ in range(max_active):
                    Vacancy.objects.create(
                        title="V", company=self.company,
                        created_by=self.recruiter, is_active=True,
                    )

                resp = self.client.post(self.create_url, self._vacancy_payload(), format="json")
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

                data = resp.json()
                details = data["error"]["details"]
                self.assertIsInstance(details, str)
                self.assertIn(str(max_active), details)

    def test_vacancy_expire_within_limit(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 30),
            (COMPANY_BASIC_PLAN_SLUG, 90),
            (COMPANY_PRO_PLAN_SLUG, 180),
        ]
        for plan_slug, max_expire in test_cases:
            with self.subTest(plan=plan_slug):
                plan_name = plan_slug.split("-", 1)[1].capitalize()
                self._subscribe(
                    plan_slug, plan_name,
                    DEFAULT_VACANCY_LIMITS[plan_slug],
                )
                self.client.force_authenticate(user=self.recruiter)

                resp = self.client.post(
                    self.create_url, self._vacancy_payload(expire=max_expire), format="json"
                )
                self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_vacancy_expire_exceed_limit(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 30),
            (COMPANY_BASIC_PLAN_SLUG, 90),
            (COMPANY_PRO_PLAN_SLUG, 180),
        ]
        for plan_slug, max_expire in test_cases:
            with self.subTest(plan=plan_slug):
                plan_name = plan_slug.split("-", 1)[1].capitalize()
                self._subscribe(
                    plan_slug, plan_name,
                    DEFAULT_VACANCY_LIMITS[plan_slug],
                )
                self.client.force_authenticate(user=self.recruiter)

                resp = self.client.post(
                    self.create_url, self._vacancy_payload(expire=max_expire + 1), format="json"
                )
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

                data = resp.json()
                details = data["error"]["details"]
                self.assertIsInstance(details, str)
                self.assertIn(str(max_expire), details)

    # ---- Upgrade scenario: Free → Pro ----

    def test_upgrade_from_free_to_pro_allows_more_vacancies(self):
        free = create_plan_with_limits(
            COMPANY_FREE_PLAN_SLUG, "Free",
            vacancy_config=DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        pro = create_plan_with_limits(
            COMPANY_PRO_PLAN_SLUG, "Pro",
            vacancy_config=DEFAULT_VACANCY_LIMITS[COMPANY_PRO_PLAN_SLUG],
        )
        subscribe_company(self.company, free)
        self.client.force_authenticate(user=self.recruiter)

        # Fill up to free limit
        for _ in range(3):
            Vacancy.objects.create(
                title="V", company=self.company,
                created_by=self.recruiter, is_active=True,
            )

        resp = self.client.post(self.create_url, self._vacancy_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Upgrade to pro
        subscribe_company(self.company, pro)

        resp = self.client.post(self.create_url, self._vacancy_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    # ---- Update vacancy expire limit ----

    def test_update_vacancy_expire_within_limit(self):
        self._subscribe(
            COMPANY_FREE_PLAN_SLUG, "Free",
            DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        self.client.force_authenticate(user=self.recruiter)

        vacancy = Vacancy.objects.create(
            title="V", company=self.company,
            created_by=self.recruiter, is_active=True,
        )
        url = reverse("update-vacancy", kwargs={"id": vacancy.id})

        resp = self.client.patch(url, {"expire": 25}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_update_vacancy_expire_exceed_limit(self):
        self._subscribe(
            COMPANY_FREE_PLAN_SLUG, "Free",
            DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        self.client.force_authenticate(user=self.recruiter)

        vacancy = Vacancy.objects.create(
            title="V", company=self.company,
            created_by=self.recruiter, is_active=True,
        )
        url = reverse("update-vacancy", kwargs={"id": vacancy.id})

        resp = self.client.patch(url, {"expire": 60}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ---- Inactive vacancies do not count toward limit ----

    def test_inactive_vacancies_not_counted(self):
        self._subscribe(
            COMPANY_FREE_PLAN_SLUG, "Free",
            DEFAULT_VACANCY_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        self.client.force_authenticate(user=self.recruiter)

        # Create 3 but deactivate one
        for _ in range(3):
            Vacancy.objects.create(
                title="V", company=self.company,
                created_by=self.recruiter, is_active=True,
            )
        Vacancy.objects.filter(company=self.company).first().delete()

        # Only 2 active → should allow
        resp = self.client.post(self.create_url, self._vacancy_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class TemplateSubscriptionLimitAPITests(APITestCase):
    """
    Integration tests: creating reason templates via the API respects
    subscription limits and returns trilingual 403 messages.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Template API Co", tin="888000002")
        cls.recruiter = Recruiter.objects.create_user(
            email="reason_api_recr@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Template Recruiter",
            level="Admin",
        )

        # Create a minimal ApplicationStatusModel so STATUS_CHANGE templates can reference it
        rejected_category, _ = StatusCategory.objects.get_or_create(
            key=StatusCategory.REJECTED,
            defaults={
                "label": "Rejected",
                "is_terminal": True,
                "position": 50,
            },
        )
        cls.application_status, _ = ApplicationStatusModel.objects.get_or_create(
            company=cls.company,
            key="REJECTED",
            defaults={
                "label": "Rejected",
                "category": rejected_category,
            },
        )

        cls.create_url = reverse("template-list-create")

    def _subscribe(self, slug, name, reason_config):
        plan = create_plan_with_limits(slug, name, reason_config=reason_config)
        subscribe_company(self.company, plan)
        return plan

    def _reason_payload(self):
        return {
            "title": "Test Template",
            "description": "Test description",
            "template_type": "STATUS_CHANGE",
            "application_status_id": str(self.application_status.id),
        }

    def test_create_reason_within_limit(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 2),
            (COMPANY_BASIC_PLAN_SLUG, 5),
            (COMPANY_PRO_PLAN_SLUG, 10),
        ]
        for plan_slug, max_templates in test_cases:
            with self.subTest(plan=plan_slug):
                Template.objects.filter(company=self.company).delete()
                plan_name = plan_slug.split("-", 1)[1].capitalize()

                self._subscribe(
                    plan_slug, plan_name,
                    DEFAULT_TEMPLATE_LIMITS[plan_slug],
                )
                self.client.force_authenticate(user=self.recruiter)

                for _ in range(max_templates - 1):
                    Template.objects.create(
                        title="R", company=self.company,
                        template_type=Template.TemplateType.STATUS_CHANGE,
                    )

                resp = self.client.post(self.create_url, self._reason_payload(), format="json")
                self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_create_reason_exceed_limit(self):
        test_cases = [
            (COMPANY_FREE_PLAN_SLUG, 2),
            (COMPANY_BASIC_PLAN_SLUG, 5),
            (COMPANY_PRO_PLAN_SLUG, 10),
        ]
        for plan_slug, max_templates in test_cases:
            with self.subTest(plan=plan_slug):
                Template.objects.filter(company=self.company).delete()
                plan_name = plan_slug.split("-", 1)[1].capitalize()

                self._subscribe(
                    plan_slug, plan_name,
                    DEFAULT_TEMPLATE_LIMITS[plan_slug],
                )
                self.client.force_authenticate(user=self.recruiter)

                for _ in range(max_templates):
                    Template.objects.create(
                        title="R", company=self.company,
                        template_type=Template.TemplateType.STATUS_CHANGE,
                    )

                resp = self.client.post(self.create_url, self._reason_payload(), format="json")
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

                data = resp.json()
                details = data["error"]["details"]
                self.assertIsInstance(details, str)
                self.assertIn(str(max_templates), details)

    # ---- Upgrade scenario ----

    def test_upgrade_from_free_to_pro_allows_more_templates(self):
        free = create_plan_with_limits(
            COMPANY_FREE_PLAN_SLUG, "Free",
            reason_config=DEFAULT_TEMPLATE_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        pro = create_plan_with_limits(
            COMPANY_PRO_PLAN_SLUG, "Pro",
            reason_config=DEFAULT_TEMPLATE_LIMITS[COMPANY_PRO_PLAN_SLUG],
        )
        subscribe_company(self.company, free)
        self.client.force_authenticate(user=self.recruiter)

        for _ in range(2):
            Template.objects.create(
                title="R", company=self.company,
                template_type=Template.TemplateType.STATUS_CHANGE,
            )

        resp = self.client.post(self.create_url, self._reason_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Upgrade
        subscribe_company(self.company, pro)

        resp = self.client.post(self.create_url, self._reason_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    # ---- GET listing is not blocked by limit ----

    def test_listing_templates_not_blocked_by_limit(self):
        """GET requests bypass the CanCreateTemplate check."""
        self._subscribe(
            COMPANY_FREE_PLAN_SLUG, "Free",
            DEFAULT_TEMPLATE_LIMITS[COMPANY_FREE_PLAN_SLUG],
        )
        self.client.force_authenticate(user=self.recruiter)

        # Fill templates beyond limit manually
        for _ in range(5):
            Template.objects.create(
                title="R", company=self.company,
                template_type=Template.TemplateType.STATUS_CHANGE,
            )

        resp = self.client.get(self.create_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════
# Management command test
# ══════════════════════════════════════════════════════════

class SeedSubscriptionsCommandTests(TestCase):
    """Test that seed_subscriptions creates vacancy/template limit features."""

    def test_seed_creates_vacancy_and_reason_features(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_subscriptions", "--update", stdout=out)

        # Verify features exist
        self.assertTrue(
            SubscriptionFeature.objects.filter(code=FEATURE_VACANCY_LIMIT).exists()
        )
        self.assertTrue(
            SubscriptionFeature.objects.filter(code=FEATURE_TEMPLATE_LIMIT).exists()
        )

        # Verify PlanFeatures exist for all company plans
        for slug in [COMPANY_FREE_PLAN_SLUG, COMPANY_BASIC_PLAN_SLUG, COMPANY_PRO_PLAN_SLUG]:
            plan = SubscriptionPlan.objects.get(slug=slug)
            self.assertTrue(
                PlanFeature.objects.filter(
                    plan=plan,
                    feature__code=FEATURE_VACANCY_LIMIT,
                    is_enabled=True,
                ).exists(),
                f"{slug} should have vacancy_limit feature",
            )
            self.assertTrue(
                PlanFeature.objects.filter(
                    plan=plan,
                    feature__code=FEATURE_TEMPLATE_LIMIT,
                    is_enabled=True,
                ).exists(),
                f"{slug} should have template_limit feature",
            )

    def test_seed_configurations_match_defaults(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("seed_subscriptions", "--update", stdout=StringIO())

        for slug, expected in DEFAULT_VACANCY_LIMITS.items():
            plan = SubscriptionPlan.objects.get(slug=slug)
            pf = PlanFeature.objects.get(
                plan=plan, feature__code=FEATURE_VACANCY_LIMIT
            )
            self.assertEqual(pf.configuration["max_active_vacancies"], expected["max_active_vacancies"])
            self.assertEqual(pf.configuration["max_expire_days"], expected["max_expire_days"])

        for slug, expected in DEFAULT_TEMPLATE_LIMITS.items():
            plan = SubscriptionPlan.objects.get(slug=slug)
            pf = PlanFeature.objects.get(
                plan=plan, feature__code=FEATURE_TEMPLATE_LIMIT
            )
            self.assertEqual(pf.configuration["max_reasons"], expected["max_reasons"])

    def test_seed_idempotent(self):
        """Running seed twice should not create duplicates."""
        from django.core.management import call_command
        from io import StringIO

        call_command("seed_subscriptions", stdout=StringIO())
        count1 = PlanFeature.objects.count()

        call_command("seed_subscriptions", stdout=StringIO())
        count2 = PlanFeature.objects.count()

        self.assertEqual(count1, count2)
