"""
Tests for company registration subscription auto-creation
and recruiter email validation with subscription limits.

Covers:
- #6: CompanySubscription created on company registration
- #6: Correct plan (free) and ACTIVE status
- #6: Graceful degradation when plan doesn't exist
- #6: No duplicate subscriptions
- #7: Recruiter limit validation during registration
- #7: Error messages for exceeded limits
"""

from unittest.mock import patch
import json

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Company
from apps.authentication.models.consent_config import ConsentConfiguration
from apps.authentication.services.consent_service import ConsentService
from apps.subscriptions.models import (
    SubscriptionPlan,
    CompanySubscription,
)
from apps.subscriptions.services import SubscriptionService


def _create_consent_configs():
    """Create the minimal consent configurations required for company registration."""
    for entity_type in ("company", "recruiter"):
        ConsentConfiguration.objects.get_or_create(
            consent_type="terms_of_service",
            entity_type=entity_type,
            is_active=True,
            defaults={"version": "1.0", "name": f"ToS ({entity_type})"},
        )


# ═══════════════════════════════════════════════════════════════
#  Company Registration → Subscription Creation Tests (#6)
# ═══════════════════════════════════════════════════════════════


class CompanyRegistrationSubscriptionTests(APITestCase):
    """
    Verify that company registration auto-creates a subscription.
    """

    URL = "/api/v1/users/companies/create/"

    @classmethod
    def setUpTestData(cls):
        _create_consent_configs()
        cls.free_plan = SubscriptionPlan.objects.create(
            name="Free",
            slug="company-free",
            plan_type="company",
            max_admins=1,
            max_recruiters=3,
        )

    def _register_company(self, name="Test Co", tin="123456789", email="admin@test.com", **kwargs):
        data = {
            "name": name,
            "inn": tin,
            "company_email": email,
            "phone_number": kwargs.get("phone_number", "+998901234567"),
            "company_agreed_to_all_consents": True,
            "admin_agreed_to_all_consents": True,
            "recruiter_emails": json.dumps(kwargs.get("recruiter_emails", [])),
        }
        return self.client.post(self.URL, data, format="multipart")

    def test_subscription_created_on_registration(self):
        resp = self._register_company()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        company = Company.objects.get(name="Test Co")
        sub = CompanySubscription.objects.filter(company=company).first()
        self.assertIsNotNone(sub)

    def test_subscription_has_free_plan(self):
        self._register_company()
        company = Company.objects.get(name="Test Co")
        sub = CompanySubscription.objects.filter(company=company).first()
        self.assertEqual(sub.plan.slug, "company-free")

    def test_subscription_is_active(self):
        self._register_company()
        company = Company.objects.get(name="Test Co")
        sub = CompanySubscription.objects.filter(company=company).first()
        self.assertEqual(sub.status, CompanySubscription.Status.ACTIVE)

    def test_no_duplicate_subscriptions(self):
        self._register_company()
        company = Company.objects.get(name="Test Co")
        count = CompanySubscription.objects.filter(
            company=company,
            status=CompanySubscription.Status.ACTIVE,
        ).count()
        self.assertEqual(count, 1)

    def test_registration_succeeds_without_plan(self):
        """Registration should not fail even if the free plan doesn't exist."""
        SubscriptionPlan.objects.filter(slug="company-free").update(is_active=False)
        resp = self._register_company(
            name="No Plan Co", tin="999999991", email="noplan@test.com",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(name="No Plan Co")
        # No subscription created
        self.assertFalse(
            CompanySubscription.objects.filter(company=company).exists()
        )
        # Restore for other tests
        SubscriptionPlan.objects.filter(slug="company-free").update(is_active=True)

    def test_warning_logged_when_subscription_creation_fails(self):
        SubscriptionPlan.objects.filter(slug="company-free").update(is_active=False)
        with self.assertLogs("apps.authentication.views.company", level="WARNING") as cm:
            self._register_company(
                name="Warn Co", tin="888888881", email="warn@test.com",
            )
        log_output = "\n".join(cm.output)
        self.assertIn("Failed to create subscription", log_output)
        SubscriptionPlan.objects.filter(slug="company-free").update(is_active=True)


# ═══════════════════════════════════════════════════════════════
#  Recruiter Email Validation with Subscription Limits (#7)
# ═══════════════════════════════════════════════════════════════


class RecruiterLimitValidationTests(APITestCase):
    """
    Verify that the CompanyRegistrationSerializer.validate_recruiter_emails
    enforces subscription recruiter limits.
    """

    URL = "/api/v1/users/companies/create/"

    @classmethod
    def setUpTestData(cls):
        _create_consent_configs()
        cls.free_plan = SubscriptionPlan.objects.create(
            name="Free",
            slug="company-free",
            plan_type="company",
            max_admins=1,
            max_recruiters=3,
        )

    def _register_company(self, recruiter_emails, **kwargs):
        data = {
            "name": kwargs.get("name", "Limit Co"),
            "inn": kwargs.get("tin", "limit123"),
            "company_email": kwargs.get("email", "limitadmin@test.com"),
            "phone_number": kwargs.get("phone_number", "+998901234567"),
            "company_agreed_to_all_consents": True,
            "admin_agreed_to_all_consents": True,
            "recruiter_emails": json.dumps(recruiter_emails),
        }
        return self.client.post(self.URL, data, format="multipart")

    def test_within_limits_succeeds(self):
        """1 admin (company_email) + 3 recruiters = within free plan limits."""
        recruiter_emails = [
            {"email": f"rec{i}@test.com", "level": "Recruiter", "agreed_to_all_consents": True}
            for i in range(3)
        ]
        resp = self._register_company(recruiter_emails, tin="910000001")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_exceeds_recruiter_limit(self):
        """1 admin + 4 recruiters > free plan limit of 3 recruiters."""
        recruiter_emails = [
            {"email": f"rec{i}@test.com", "level": "Recruiter", "agreed_to_all_consents": True}
            for i in range(4)
        ]
        resp = self._register_company(
            recruiter_emails, name="Over Co", tin="910000002",
            email="overadmin@test.com",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_exceeds_admin_limit(self):
        """1 company_email admin + 1 extra admin = 2 admins > free plan limit of 1."""
        recruiter_emails = [
            {"email": "extra_admin@test.com", "level": "Admin", "agreed_to_all_consents": True},
        ]
        resp = self._register_company(
            recruiter_emails, name="Admin Over Co", tin="910000003",
            email="admover@test.com",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_error_message_mentions_limit(self):
        """Error message should explain the limit."""
        recruiter_emails = [
            {"email": f"rec{i}@test.com", "level": "Recruiter", "agreed_to_all_consents": True}
            for i in range(4)
        ]
        resp = self._register_company(
            recruiter_emails, name="Msg Co", tin="910000004",
            email="msgadmin@test.com",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # The error should contain info about recruiter limits
        errors = str(resp.data)
        self.assertTrue(
            "recruiter" in errors.lower() or "limit" in errors.lower(),
            f"Expected limit error details, got: {resp.data}",
        )

    def test_zero_extra_recruiters_succeeds(self):
        """Just the admin email, no extra recruiters — always within limits."""
        resp = self._register_company(
            [], name="Solo Co", tin="910000005", email="solo@test.com",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class CompanyRegistrationFileValidationTests(APITestCase):
    URL = "/api/v1/users/companies/create/"

    @classmethod
    def setUpTestData(cls):
        _create_consent_configs()
        cls.free_plan = SubscriptionPlan.objects.create(
            name="Free",
            slug="company-free",
            plan_type="company",
            max_admins=1,
            max_recruiters=3,
        )

    def _register_company_with_file(self, upload_file, **kwargs):
        data = {
            "name": kwargs.get("name", "File Validation Co"),
            "inn": kwargs.get("tin", "123456789"),
            "company_email": kwargs.get("email", "file-validation@test.com"),
            "phone_number": kwargs.get("phone_number", "+998901234567"),
            "company_agreed_to_all_consents": True,
            "admin_agreed_to_all_consents": True,
            "recruiter_emails": json.dumps([]),
            "file": upload_file,
        }
        return self.client.post(self.URL, data, format="multipart")

    def test_registration_rejects_invalid_company_file_format(self):
        invalid_file = SimpleUploadedFile(
            "company_script.exe",
            b"dummy content",
            content_type="application/octet-stream",
        )

        with patch(
            "apps.authentication.serializers.recruiter.validate_uploaded_file",
            side_effect=lambda file_obj: file_obj,
        ):
            response = self._register_company_with_file(
                invalid_file,
                name="Invalid Format Co",
                tin="123456781",
                email="invalid-format@test.com",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data["error"]["field_errors"])
        self.assertIn(
            "Invalid file format",
            str(response.data["error"]["field_errors"]["file"]),
        )

    def test_registration_rejects_company_file_larger_than_5mb(self):
        large_pdf = SimpleUploadedFile(
            "company_document.pdf",
            b"a" * (settings.MAX_FILE_SIZE + 1),
            content_type="application/pdf",
        )

        with patch(
            "apps.authentication.serializers.recruiter.validate_uploaded_file",
            side_effect=lambda file_obj: file_obj,
        ):
            response = self._register_company_with_file(
                large_pdf,
                name="Large File Co",
                tin="123456782",
                email="large-file@test.com",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data["error"]["field_errors"])
        self.assertIn("5MB", str(response.data["error"]["field_errors"]["file"]))


class CheckRecruiterLimitServiceTests(TestCase):
    """
    Direct tests for SubscriptionService.check_recruiter_limit.
    (Complements the serializer-level tests above.)
    """

    @classmethod
    def setUpTestData(cls):
        cls.free_plan = SubscriptionPlan.objects.create(
            name="Free", slug="company-free", plan_type="company",
            max_admins=1, max_recruiters=3,
        )

    def test_new_company_exactly_at_admin_limit(self):
        result = SubscriptionService.check_recruiter_limit(None, 1, 0)
        self.assertTrue(result["allowed"])

    def test_new_company_exceeds_admin_limit(self):
        result = SubscriptionService.check_recruiter_limit(None, 2, 0)
        self.assertFalse(result["allowed"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("admin", result["errors"][0].lower())

    def test_new_company_exactly_at_recruiter_limit(self):
        result = SubscriptionService.check_recruiter_limit(None, 1, 3)
        self.assertTrue(result["allowed"])

    def test_new_company_exceeds_recruiter_limit(self):
        result = SubscriptionService.check_recruiter_limit(None, 1, 4)
        self.assertFalse(result["allowed"])

    def test_both_limits_exceeded(self):
        result = SubscriptionService.check_recruiter_limit(None, 5, 10)
        self.assertFalse(result["allowed"])
        self.assertEqual(len(result["errors"]), 2)


class ConsentServiceQueryOptimizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ConsentConfiguration.objects.create(
            consent_type="terms_of_service",
            entity_type="company",
            version="1.0",
            name="Company Terms",
            is_active=True,
        )

    def test_validate_entity_type_reuses_request_cache(self):
        request = RequestFactory().post("/api/v1/users/companies/create/")

        with self.assertNumQueries(1):
            is_valid, error_msg, consents = ConsentService.validate_entity_type(
                "company",
                request=request,
            )

        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)
        self.assertEqual(len(consents), 1)

    def test_create_consents_for_entity_uses_single_insert_without_userconsent_select(self):
        company = Company.objects.create(name="Consent Query Co", tin="912345678")
        request = RequestFactory().post("/api/v1/users/companies/create/")

        with CaptureQueriesContext(connection) as queries:
            ConsentService.create_consents_for_entity(
                consenter=company,
                entity_type="company",
                ip_address="127.0.0.1",
                user_agent="test-agent",
                request=request,
            )

        insert_count = 0
        for query in queries.captured_queries:
            sql = query.get("sql", "").lower()
            if "insert into \"authentication_userconsent\"" in sql:
                insert_count += 1
            self.assertNotIn("from \"authentication_userconsent\"", sql)

        self.assertEqual(insert_count, 1)

        with self.assertNumQueries(0):
            is_valid, error_msg, consents = ConsentService.validate_entity_type(
                "company",
                request=request,
            )

        self.assertTrue(is_valid)
        self.assertIsNone(error_msg)
        self.assertEqual(len(consents), 1)
