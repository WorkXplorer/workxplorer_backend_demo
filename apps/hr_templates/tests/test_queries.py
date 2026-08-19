from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.hr_templates.models import Template
from apps.authentication.models.recruiter import Company, Recruiter
from apps.profiles.models import RecruiterProfile
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
)
from apps.subscriptions.services import FEATURE_TEMPLATE_LIMIT


class TemplateAPIQueryCountTests(APITestCase):
    """
    Tests to ensure the Template CRUD APIs do not have duplicate/N+1 queries.
    Uses Django's assertNumQueries to verify query count.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Query Test Company", tin="400000001")
        cls.recruiter = Recruiter.objects.create_user(
            email="query_recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Query Recruiter",
            level="Admin",
        )

        # ── Subscription setup (Pro plan with high limits) ──
        plan = SubscriptionPlan.objects.create(
            name="Pro",
            slug="company-pro",
            plan_type="company",
            is_active=True,
            max_admins=10,
            max_recruiters=50,
        )
        feature, _ = SubscriptionFeature.objects.get_or_create(
            name="Template Limit",
            code=FEATURE_TEMPLATE_LIMIT,
        )
        PlanFeature.objects.create(
            plan=plan,
            feature=feature,
            is_enabled=True,
            configuration={"max_reasons": 100},
        )
        CompanySubscription.objects.create(
            company=cls.company,
            plan=plan,
            status="active",
        )

        # Create multiple templates to expose N+1 issues
        for i in range(10):
            Template.objects.create(
                title=f"Template {i}",
                description=f"Description for template {i}",
                company=cls.company,
                template_type=Template.TemplateType.INVITATION,
            )

        cls.list_url = reverse("template-list-create")

    def test_list_query_count_does_not_grow_with_items(self):
        """
        Listing templates should use a constant number of queries,
        regardless of how many templates exist (no N+1 problem).

        Expected queries (GET — subscription permission skips limit check):
        Recruiter lookup is in-memory (force_authenticate sets request.user directly).
        1. SELECT COUNT(*) for pagination
        2. SELECT templates for company
        """
        self.client.force_authenticate(user=self.recruiter)

        # Warm up any caches
        self.client.get(self.list_url)

        with self.assertNumQueries(2):
            response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        # Handle both {"data": {"results": [...]}} and {"data": [...]} formats
        data = body.get("data", body)
        if isinstance(data, dict):
            data = data.get("results", data)
        self.assertGreaterEqual(len(data), 10)

    def test_create_query_count(self):
        """
        Creating a template should use a minimal number of queries.

        Note: recruiter lookup is NOT needed because
        _resolve_subscription_context caches the user as _recruiter_cache
        when user.company is directly accessible.
        """
        self.client.force_authenticate(user=self.recruiter)

        # Warm up
        self.client.get(self.list_url)

        with self.assertNumQueries(4):
            response = self.client.post(
                self.list_url,
                {
                    "title": "New query-counted template",
                    "description": "Test",
                    "template_type": "INVITATION",
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_retrieve_query_count(self):
        """
        Retrieving a single template should use a minimal number of queries.

        Expected queries:
        Recruiter lookup is in-memory (force_authenticate sets request.user directly).
        1. SELECT template by id + company
        """
        template = Template.objects.filter(company=self.company).first()
        url = reverse("template-detail", kwargs={"template_id": template.id})

        self.client.force_authenticate(user=self.recruiter)

        # Warm up
        self.client.get(url)

        with self.assertNumQueries(1):
            response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_query_count(self):
        """
        Deleting a template should use a minimal number of queries.

        Expected queries (DELETE — no subscription permission check):
        Recruiter lookup is in-memory (force_authenticate sets request.user directly).
        1. SELECT template by id + company
        2. DELETE template
        """
        template = Template.objects.create(
            title="To delete for query test",
            description="Will be deleted",
            company=self.company,
            template_type=Template.TemplateType.INVITATION,
        )
        url = reverse("template-detail", kwargs={"template_id": template.id})

        self.client.force_authenticate(user=self.recruiter)

        # Warm up
        self.client.get(reverse("template-list-create"))

        with self.assertNumQueries(2):
            response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
