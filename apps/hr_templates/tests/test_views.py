from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from apps.hr_templates.models import Template
from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.profiles.models import RecruiterProfile
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
)
from apps.subscriptions.services import FEATURE_TEMPLATE_LIMIT


def _setup_pro_subscription(company):
    """Create a Pro plan with a generous template limit for test isolation."""
    plan, _ = SubscriptionPlan.objects.get_or_create(
        slug="company-pro",
        defaults={
            "name": "Pro",
            "plan_type": "company",
            "max_admins": 3,
            "max_recruiters": 10,
            "price": 0,
            "display_order": 3,
        },
    )
    feature, _ = SubscriptionFeature.objects.get_or_create(
        code=FEATURE_TEMPLATE_LIMIT,
        defaults={"name": "Template Limit", "feature_type": "company"},
    )
    PlanFeature.objects.get_or_create(
        plan=plan,
        feature=feature,
        defaults={"is_enabled": True, "configuration": {"max_reasons": 10}},
    )
    CompanySubscription.objects.get_or_create(
        company=company,
        status=CompanySubscription.Status.ACTIVE,
        defaults={"plan": plan},
    )


class TemplateListCreateViewTests(APITestCase):
    """
    Test suite for the TemplateListCreateView API endpoint.
    Covers listing and creating templates for a recruiter's company.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company1 = Company.objects.create(name="HR Company 1", tin="100000001")
        cls.company2 = Company.objects.create(name="HR Company 2", tin="100000002")

        # Set up Pro subscriptions so limit checks don't interfere
        _setup_pro_subscription(cls.company1)
        _setup_pro_subscription(cls.company2)

        cls.recruiter_user = Recruiter.objects.create_user(
            email="hr_recruiter@company1.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company1,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter_user,
            full_name="HR Recruiter",
            level="Admin",
        )

        cls.recruiter_user2 = Recruiter.objects.create_user(
            email="hr_recruiter@company2.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company2,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter_user2,
            full_name="HR Recruiter 2",
            level="Admin",
        )

        cls.candidate_user = Candidate.objects.create_user(
            email="hr_candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Pre-create some templates for company1
        cls.template1 = Template.objects.create(
            title="Not enough experience",
            description="Candidate does not meet minimum experience requirements.",
            company=cls.company1,
            template_type=Template.TemplateType.INVITATION,
        )
        cls.template2 = Template.objects.create(
            title="Salary mismatch",
            description="Expected salary exceeds budget.",
            company=cls.company1,
            template_type=Template.TemplateType.INVITATION,
        )
        # Reason for company2 - should NOT appear in company1 queries
        cls.template_other_company = Template.objects.create(
            title="Other company template",
            description="Belongs to company2.",
            company=cls.company2,
            template_type=Template.TemplateType.INVITATION,
        )

        cls.list_url = reverse("template-list-create")

    # ---- Authentication tests ----

    def test_list_requires_authentication(self):
        """Unauthenticated users cannot list templates → 401."""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_requires_authentication(self):
        """Unauthenticated users cannot create templates → 401."""
        response = self.client.post(
            self.list_url, {"title": "Test", "description": "Desc"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_candidate_cannot_list_templates(self):
        """Candidates should not access templates → 403."""
        self.client.force_authenticate(user=self.candidate_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_candidate_cannot_create_template(self):
        """Candidates should not create templates → 403."""
        self.client.force_authenticate(user=self.candidate_user)
        response = self.client.post(
            self.list_url, {"title": "Test", "description": "Desc"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # ---- List tests ----

    def test_list_returns_only_own_company_templates(self):
        """
        Recruiter should only see templates belonging to their company.
        Company2's templates should not appear.
        """
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(len(data), 2)
        titles = {r["title"] for r in data}
        self.assertIn("Not enough experience", titles)
        self.assertIn("Salary mismatch", titles)
        self.assertNotIn("Other company template", titles)

    def test_list_response_fields(self):
        """Verify that list response contains the expected fields."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertGreater(len(data), 0)
        first = data[0]
        self.assertIn("id", first)
        self.assertIn("title", first)
        self.assertIn("description", first)
        self.assertIn("created_at", first)
        self.assertIn("updated_at", first)

    def test_company2_recruiter_sees_own_templates(self):
        """Company2 recruiter should only see their own templates."""
        self.client.force_authenticate(user=self.recruiter_user2)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Other company template")

    # ---- Create tests ----

    def test_create_template_success(self):
        """Recruiter can create a new template."""
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Failed technical test",
            "description": "Candidate did not pass the coding challenge.",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["title"], payload["title"])
        self.assertEqual(data["description"], payload["description"])
        # Verify it was saved to DB with correct company
        template = Template.objects.get(id=data["id"])
        self.assertEqual(template.company, self.company1)

    def test_create_template_without_description(self):
        """Description is optional, defaults to empty string."""
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {"title": "No description reason", "template_type": "INVITATION"}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["description"], "")

    def test_create_template_empty_title_fails(self):
        """Title is required and cannot be blank → 400."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.post(
            self.list_url, {"title": "", "description": "Some desc"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_template_missing_title_fails(self):
        """Title field is required → 400."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.post(
            self.list_url, {"description": "Some desc"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_template_whitespace_title_fails(self):
        """Title with only whitespace should be rejected → 400."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.post(
            self.list_url, {"title": "   ", "description": "Desc"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TemplateDetailViewTests(APITestCase):
    """
    Test suite for the TemplateDetailView API endpoint.
    Covers retrieve, update (PUT/PATCH), and delete operations.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company1 = Company.objects.create(name="Detail Company 1", tin="200000001")
        cls.company2 = Company.objects.create(name="Detail Company 2", tin="200000002")

        cls.recruiter_user = Recruiter.objects.create_user(
            email="detail_recruiter@company1.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company1,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter_user,
            full_name="Detail Recruiter",
            level="Admin",
        )

        cls.recruiter_user2 = Recruiter.objects.create_user(
            email="detail_recruiter@company2.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company2,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter_user2,
            full_name="Detail Recruiter 2",
            level="Admin",
        )

        cls.candidate_user = Candidate.objects.create_user(
            email="detail_candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        cls.template = Template.objects.create(
            title="Culture fit",
            description="Candidate is not a good culture fit.",
            company=cls.company1,
            template_type=Template.TemplateType.INVITATION,
        )

        cls.template_other_company = Template.objects.create(
            title="Other template",
            description="Belongs to company2.",
            company=cls.company2,
            template_type=Template.TemplateType.INVITATION,
        )

    def get_detail_url(self, template_id):
        return reverse("template-detail", kwargs={"template_id": template_id})

    # ---- Authentication / Permission tests ----

    def test_retrieve_requires_authentication(self):
        """Unauthenticated users cannot retrieve → 401."""
        response = self.client.get(self.get_detail_url(self.template.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_candidate_cannot_retrieve(self):
        """Candidates cannot access template detail → 403."""
        self.client.force_authenticate(user=self.candidate_user)
        response = self.client.get(self.get_detail_url(self.template.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_retrieve_other_company_reason(self):
        """Recruiter cannot see templates of another company → 404."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.get(self.get_detail_url(self.template_other_company.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---- Retrieve tests ----

    def test_retrieve_template_success(self):
        """Recruiter can retrieve their own company's template."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.get(self.get_detail_url(self.template.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()["data"]
        self.assertEqual(data["title"], "Culture fit")
        self.assertEqual(data["description"], "Candidate is not a good culture fit.")

    def test_retrieve_nonexistent_template_returns_404(self):
        """Retrieving non-existent template → 404."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.get(
            self.get_detail_url("11111111-1111-1111-1111-111111111111")
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---- Update (PUT) tests ----

    def test_full_update_template_success(self):
        """Recruiter can fully update a template via PUT."""
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Updated culture fit",
            "description": "Updated description for culture fit.",
            "template_type": "INVITATION",
        }
        response = self.client.put(
            self.get_detail_url(self.template.id), payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.template.refresh_from_db()
        self.assertEqual(self.template.title, "Updated culture fit")
        self.assertEqual(
            self.template.description, "Updated description for culture fit."
        )

    def test_full_update_empty_title_fails(self):
        """PUT with empty title → 400."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.put(
            self.get_detail_url(self.template.id),
            {"title": "", "description": "Desc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_update_other_company_template(self):
        """Recruiter cannot update templates of another company → 404."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.put(
            self.get_detail_url(self.template_other_company.id),
            {"title": "Hacked", "description": "Hacked desc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ---- Partial Update (PATCH) tests ----

    def test_partial_update_title_only(self):
        """Recruiter can PATCH just the title."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.patch(
            self.get_detail_url(self.template.id),
            {"title": "Partially updated title"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.template.refresh_from_db()
        self.assertEqual(self.template.title, "Partially updated title")

    def test_partial_update_description_only(self):
        """Recruiter can PATCH just the description."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.patch(
            self.get_detail_url(self.template.id),
            {"description": "New partial description"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.template.refresh_from_db()
        self.assertEqual(self.template.description, "New partial description")

    # ---- Delete tests ----

    def test_delete_template_success(self):
        """Recruiter can delete their own company's template."""
        template_to_delete = Template.objects.create(
            title="Delete me",
            description="To be deleted.",
            company=self.company1,
        )
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.delete(self.get_detail_url(template_to_delete.id))
        # Custom destroy() uses APIResponse.success() which returns 200
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Template.objects.filter(id=template_to_delete.id).exists())

    def test_cannot_delete_other_company_template(self):
        """Recruiter cannot delete another company's template → 404."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.delete(
            self.get_detail_url(self.template_other_company.id)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_nonexistent_template_returns_404(self):
        """Deleting a non-existent template → 404."""
        self.client.force_authenticate(user=self.recruiter_user)
        response = self.client.delete(
            self.get_detail_url("11111111-1111-1111-1111-111111111111")
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_requires_authentication(self):
        """Unauthenticated users cannot delete → 401."""
        response = self.client.delete(self.get_detail_url(self.template.id))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TemplateVariableValidationTests(APITestCase):
    """
    Test suite for variable substitution validation in template descriptions.
    Ensures only known variables are accepted.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Var Test Company", tin="300000001")
        _setup_pro_subscription(cls.company)
        cls.recruiter_user = Recruiter.objects.create_user(
            email="var_recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter_user,
            full_name="Var Recruiter",
            level="Admin",
        )
        cls.list_url = reverse("template-list-create")

    # ---- Known variables should be accepted ----

    def test_known_variables_accepted_on_create(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Invitation",
            "description": "Hello {{candidate_name}}, welcome to {{company_name}}!",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_localized_variables_accepted_on_create(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Uzbek invitation",
            "description": "Salom {{nomzod_ismi}}, {{kompaniya_nomi}} ga xush kelibsiz!",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_russian_variables_accepted_on_create(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Russian invitation",
            "description": "Здравствуйте, {{имя_кандидата}}!",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_all_three_variables_accepted(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Full template",
            "description": "{{candidate_name}}, {{position}}, {{company_name}}",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ---- Unknown variables should be rejected ----

    def test_unknown_variable_rejected_on_create(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Bad template",
            "description": "Hello {{unknown_var}}!",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_multiple_unknown_variables_rejected(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Bad template",
            "description": "{{bad1}} {{bad2}} {{bad3}}",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_variable_alongside_known_rejected(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Mixed template",
            "description": "{{candidate_name}} {{bad_var}}",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ---- Update validation ----

    def test_unknown_variable_rejected_on_update(self):
        self.client.force_authenticate(user=self.recruiter_user)
        template = Template.objects.create(
            title="Original",
            description="Original text with {{candidate_name}}",
            company=self.company,
            template_type="INVITATION",
        )
        detail_url = reverse("template-detail", kwargs={"template_id": template.id})
        response = self.client.patch(
            detail_url,
            {"description": "Now has {{bad_variable}}"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ---- Empty description ----

    def test_empty_description_accepted(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "No description",
            "description": "",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_description_without_variables_accepted(self):
        self.client.force_authenticate(user=self.recruiter_user)
        payload = {
            "title": "Plain text",
            "description": "Just some plain text without any variables.",
            "template_type": "INVITATION",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class VariableListViewTests(APITestCase):
    """Tests for the VariableListView endpoint."""

    def setUp(self):
        self.variables_url = reverse("template-variables")

    def test_variable_list_returns_all_variables(self):
        response = self.client.get(self.variables_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variables = response.json()["data"]["variables"]
        keys = {v["key"] for v in variables}
        self.assertEqual(keys, {"candidate_name", "position", "company_name"})

    def test_variable_list_has_required_fields(self):
        response = self.client.get(self.variables_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variables = response.json()["data"]["variables"]
        for v in variables:
            self.assertIn("key", v)
            self.assertIn("description", v)
            self.assertIn("localized_form", v)

    def test_variable_list_english_localized_form(self):
        response = self.client.get(self.variables_url, HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variables = response.json()["data"]["variables"]
        forms = {v["key"]: v["localized_form"] for v in variables}
        self.assertEqual(forms["candidate_name"], "{{candidate_name}}")
        self.assertEqual(forms["position"], "{{position}}")
        self.assertEqual(forms["company_name"], "{{company_name}}")

    def test_variable_list_uzbek_localized_form(self):
        response = self.client.get(self.variables_url, HTTP_ACCEPT_LANGUAGE="uz")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variables = response.json()["data"]["variables"]
        forms = {v["key"]: v["localized_form"] for v in variables}
        self.assertEqual(forms["candidate_name"], "{{nomzod_ismi}}")
        self.assertEqual(forms["position"], "{{lavozim}}")
        self.assertEqual(forms["company_name"], "{{kompaniya_nomi}}")

    def test_variable_list_russian_localized_form(self):
        response = self.client.get(self.variables_url, HTTP_ACCEPT_LANGUAGE="ru")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variables = response.json()["data"]["variables"]
        forms = {v["key"]: v["localized_form"] for v in variables}
        self.assertEqual(forms["candidate_name"], "{{имя_кандидата}}")
        self.assertEqual(forms["position"], "{{должность}}")
        self.assertEqual(forms["company_name"], "{{название_компании}}")

    def test_variable_list_descriptions_are_present(self):
        response = self.client.get(self.variables_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        variables = response.json()["data"]["variables"]
        for v in variables:
            self.assertGreater(len(v["description"]), 0)

    def test_variable_list_allows_unauthenticated(self):
        response = self.client.get(self.variables_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.json())
        self.assertIn("variables", response.json()["data"])
