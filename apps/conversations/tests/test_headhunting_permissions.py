"""
Tests for headhunting subscription permission enforcement.

Ensures that the HasHeadhuntingAccess permission on headhunting views
correctly gates access based on the recruiter's company subscription plan.

Covers:
- Free plan recruiters receive 403 on HeadhuntingCandidateListView
- Free plan recruiters receive 403 on HeadhuntingInvitationView
- Basic/Pro plan recruiters successfully access these endpoints
- Appropriate error messages
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.authentication.models import Company, Recruiter, Candidate
from apps.profiles.models import RecruiterProfile, CandidateProfile
from apps.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionFeature,
    PlanFeature,
    CompanySubscription,
)


class HeadhuntingSubscriptionPermissionTests(APITestCase):
    """
    Verify that headhunting views enforce HasHeadhuntingAccess permission.
    """

    CANDIDATES_URL = "/api/v1/conversations/headhunting/candidates/"
    INVITE_URL = "/api/v1/conversations/headhunting/invite/"

    @classmethod
    def setUpTestData(cls):
        # ── Plans ──────────────────────────────────────────
        cls.free_plan = SubscriptionPlan.objects.create(
            name="Free", slug="hh-perm-free", plan_type="company",
            max_admins=1, max_recruiters=3,
        )
        cls.basic_plan = SubscriptionPlan.objects.create(
            name="Basic", slug="hh-perm-basic", plan_type="company",
            max_admins=2, max_recruiters=5,
        )

        # ── Feature ────────────────────────────────────────
        cls.hh_feature, _ = SubscriptionFeature.objects.get_or_create(
            code="headhunting_access",
            defaults={"name": "Headhunting Access", "feature_type": "company"},
        )
        PlanFeature.objects.create(
            plan=cls.basic_plan, feature=cls.hh_feature, is_enabled=True,
        )
        # Free plan intentionally has NO headhunting feature.

        # ── Free-plan company + recruiter ──────────────────
        cls.free_company = Company.objects.create(
            name="Free Co", tin="hhperm111", is_active=True,
        )
        CompanySubscription.objects.create(
            company=cls.free_company, plan=cls.free_plan,
            status=CompanySubscription.Status.ACTIVE,
        )
        cls.free_recruiter = Recruiter.objects.create_user(
            email="hhperm.free@test.com", password="testpass123",
            is_recruiter=True, company=cls.free_company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.free_recruiter, full_name="Free Recruiter",
        )

        # ── Basic-plan company + recruiter ─────────────────
        cls.basic_company = Company.objects.create(
            name="Basic Co", tin="hhperm222", is_active=True,
        )
        CompanySubscription.objects.create(
            company=cls.basic_company, plan=cls.basic_plan,
            status=CompanySubscription.Status.ACTIVE,
        )
        cls.basic_recruiter = Recruiter.objects.create_user(
            email="hhperm.basic@test.com", password="testpass123",
            is_recruiter=True, company=cls.basic_company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.basic_recruiter, full_name="Basic Recruiter",
        )

        # ── Candidate (needed so the list view has data) ───
        cls.candidate = Candidate.objects.create_user(
            email="hhperm.candidate@test.com", password="testpass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=cls.candidate, full_name="Test Candidate",
            phone="+998900000000",
        )

    # ── HeadhuntingCandidateListView ───────────────────────

    def test_candidates_view_denies_free_plan_recruiter(self):
        self.client.force_authenticate(user=self.free_recruiter)
        resp = self.client.get(self.CANDIDATES_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_candidates_view_allows_basic_plan_recruiter(self):
        self.client.force_authenticate(user=self.basic_recruiter)
        resp = self.client.get(self.CANDIDATES_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_candidates_view_error_message(self):
        self.client.force_authenticate(user=self.free_recruiter)
        resp = self.client.get(self.CANDIDATES_URL)
        # DRF may return the message under 'detail' or in a list
        response_text = str(resp.data)
        self.assertIn("Upgrade to Basic or Pro", response_text)

    # ── HeadhuntingInvitationView ──────────────────────────

    def test_invite_view_denies_free_plan_recruiter(self):
        self.client.force_authenticate(user=self.free_recruiter)
        resp = self.client.post(self.INVITE_URL, {
            "candidate_ids": [str(self.candidate.pk)],
            "letter": "Hello, we would like to invite you.",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_invite_view_allows_basic_plan_recruiter(self):
        """Basic recruiter can POST to /invite/ — may get validation
        errors on content, but should not get a 403."""
        self.client.force_authenticate(user=self.basic_recruiter)
        resp = self.client.post(self.INVITE_URL, {
            "candidate_ids": [str(self.candidate.pk)],
            "letter": "Hello, we would like to invite you to join our team.",
        }, format="json")
        # Expect 200/201 or validation error, but NOT 403
        self.assertNotEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── Unauthenticated ───────────────────────────────────

    def test_candidates_view_denies_unauthenticated(self):
        resp = self.client.get(self.CANDIDATES_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invite_view_denies_unauthenticated(self):
        resp = self.client.post(self.INVITE_URL, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
