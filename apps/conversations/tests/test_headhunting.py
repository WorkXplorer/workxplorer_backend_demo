from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.vacancies.models import Vacancy
from apps.conversations.models import Conversation, Message
from apps.profiles.models import CandidateProfile, RecruiterProfile
from apps.authentication.models import Candidate, Recruiter, Company
from apps.subscriptions.models import SubscriptionPlan, SubscriptionFeature, PlanFeature, CompanySubscription


def create_headhunting_subscription(company):
    """Helper to create a subscription with headhunting_access for a company."""
    plan = SubscriptionPlan.objects.create(
        name="Pro",
        slug=f"company-pro-{company.pk}",
        plan_type=SubscriptionPlan.PlanType.COMPANY,
        is_active=True,
    )
    feature, _ = SubscriptionFeature.objects.get_or_create(
        code="headhunting_access",
        defaults={
            "name": "Headhunting Access",
            "feature_type": SubscriptionFeature.FeatureType.COMPANY,
        },
    )
    PlanFeature.objects.create(plan=plan, feature=feature, is_enabled=True)
    CompanySubscription.objects.create(
        company=company,
        plan=plan,
        status=CompanySubscription.Status.ACTIVE,
    )


class HeadhuntingCandidateListViewTests(APITestCase):
    """Tests for HeadhuntingCandidateListView."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

        # Create a company
        self.company = Company.objects.create(
            name="Tech Corp",
            tin="987654321",
            is_active=True,
        )

        # Create a recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="hr@techcorp.com",
            password="securepass123",
            is_recruiter=True,
            company=self.company,
        )

        # Create recruiter profile
        self.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="HR Manager",
        )

        # Create subscription with headhunting access
        create_headhunting_subscription(self.company)

        # Create candidates with resumes
        self._create_test_candidates()

    def _create_test_candidates(self):
        """Create test candidates with various profiles and resumes."""
        from apps.resumes.models import Resume, ResumeExperience
        from apps.resumes.models.choices import WorkStatus
        from decimal import Decimal

        # Candidate 1: Senior developer, actively looking
        self.candidate1 = Candidate.objects.create_user(
            email="senior.dev@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate1_profile = CandidateProfile.objects.create(
            candidate=self.candidate1,
            full_name="John Senior",
            phone="+998901234567",
        )
        self.resume1 = Resume.objects.create(
            candidate=self.candidate1,
            title="Senior Python Developer",
            description="Experienced Python developer",
            position="Senior Developer",
            work_status=WorkStatus.ACTIVELY_LOOKING,
            current_salary=Decimal("5000.00"),
            salary_currency="USD",
            is_active=True,
            is_main=True,
        )
        # Add ~7 years of experience (non-overlapping)
        ResumeExperience.objects.create(
            resume=self.resume1,
            company="TechCorp",
            role="Python Developer",
            start_date=date(2019, 1, 1),
            end_date=date(2023, 1, 1),
        )
        ResumeExperience.objects.create(
            resume=self.resume1,
            company="StartupXYZ",
            role="Junior Developer",
            start_date=date(2016, 1, 1),
            end_date=date(2019, 1, 1),
        )

        # Candidate 2: Junior developer, open to opportunities
        self.candidate2 = Candidate.objects.create_user(
            email="junior.dev@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate2_profile = CandidateProfile.objects.create(
            candidate=self.candidate2,
            full_name="Jane Junior",
            phone="+998907654321",
        )
        self.resume2 = Resume.objects.create(
            candidate=self.candidate2,
            title="Junior Developer",
            description="Eager to learn",
            position="Junior Developer",
            work_status=WorkStatus.OPEN_TO_OPPORTUNITIES,
            current_salary=Decimal("1500.00"),
            salary_currency="USD",
            is_active=True,
            is_main=True,
        )
        ResumeExperience.objects.create(
            resume=self.resume2,
            company="InternCorp",
            role="Intern",
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 1),
        )

        # Candidate 3: Mid-level, not actively looking
        self.candidate3 = Candidate.objects.create_user(
            email="mid.dev@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate3_profile = CandidateProfile.objects.create(
            candidate=self.candidate3,
            full_name="Mike Mid",
        )
        self.resume3 = Resume.objects.create(
            candidate=self.candidate3,
            title="Mid-level Developer",
            description="Solid experience",
            position="Developer",
            work_status=WorkStatus.NOT_LOOKING,
            current_salary=Decimal("3000.00"),
            salary_currency="USD",
            is_active=True,
            is_main=True,
        )
        ResumeExperience.objects.create(
            resume=self.resume3,
            company="SomeCorp",
            role="Developer",
            start_date=date(2022, 1, 1),
            end_date=date(2025, 1, 1),
        )

        # Candidate 4: Inactive resume (should not appear)
        self.candidate4 = Candidate.objects.create_user(
            email="inactive@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate4_profile = CandidateProfile.objects.create(
            candidate=self.candidate4,
            full_name="Inactive User",
        )
        self.resume4 = Resume.objects.create(
            candidate=self.candidate4,
            title="Old Resume",
            description="No longer active",
            position="Developer",
            work_status=WorkStatus.ACTIVELY_LOOKING,
            is_active=False,  # Inactive!
            is_main=True,
        )

    def test_list_candidates_requires_authentication(self):
        """Test that unauthenticated users cannot access the endpoint."""
        response = self.client.get("/api/v1/conversations/headhunting/candidates/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_candidates_requires_recruiter_permission(self):
        """Test that only recruiters can access the endpoint."""
        self.client.force_authenticate(user=self.candidate1)
        response = self.client.get("/api/v1/conversations/headhunting/candidates/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_candidates_returns_active_resumes_only(self):
        """Test that only active resumes are returned."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get("/api/v1/conversations/headhunting/candidates/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle paginated response
        results = response.data.get("data", response.data.get("results", response.data))

        # Should have 3 active resumes (candidate4 has inactive resume)
        self.assertEqual(len(results), 3)

        # Verify inactive resume is not included
        candidate_emails = [r["candidate_email"] for r in results]
        self.assertNotIn("inactive@email.com", candidate_emails)

    def test_search_by_name(self):
        """Test search filter by candidate name."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"search": "John Senior"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["full_name"], "John Senior")

    def test_search_by_position(self):
        """Test search filter by position."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"search": "Senior Developer"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["position"], "Senior Developer")

    def test_filter_by_salary_min(self):
        """Test salary minimum filter."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"salary_min": 3000, "currency": "USD"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Should get candidate1 ($5000) and candidate3 ($3000)
        self.assertEqual(len(results), 2)
        for r in results:
            # Salary is formatted as string with spaces (e.g. "5 000")
            salary_value = int(r["current_salary"].replace(" ", ""))
            self.assertGreaterEqual(salary_value, 3000)

    def test_filter_by_salary_max(self):
        """Test salary maximum filter."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"salary_max": 2000, "currency": "USD"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Should only get candidate2 ($1500)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["current_salary"], "1 500")

    def test_filter_by_salary_range(self):
        """Test salary range filter (min and max)."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"salary_min": 2000, "salary_max": 4000, "currency": "USD"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Should only get candidate3 ($3000)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["current_salary"], "3 000")

    def test_filter_by_experience(self):
        """Test minimum experience filter."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"experience": 5}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Should only get candidate1 (7 years)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["full_name"], "John Senior")

    def test_filter_by_experience_excludes_no_experience(self):
        """Test that experience filter excludes candidates with no experience data."""
        from apps.resumes.models import Resume
        from apps.resumes.models.choices import WorkStatus

        # Create a candidate with no experience
        candidate_no_exp = Candidate.objects.create_user(
            email="noexp@email.com",
            password="testpass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=candidate_no_exp,
            full_name="No Experience",
        )
        Resume.objects.create(
            candidate=candidate_no_exp,
            title="Fresh Graduate",
            description="No experience yet",
            position="Developer",
            work_status=WorkStatus.ACTIVELY_LOOKING,
            is_active=True,
            is_main=True,
        )

        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"experience": 2}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Candidates with no experience should NOT be included
        candidate_names = [r["full_name"] for r in results]
        self.assertNotIn("No Experience", candidate_names)

    def test_filter_by_work_status(self):
        """Test work status filter."""
        from apps.resumes.models.choices import WorkStatus

        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"work_status": WorkStatus.ACTIVELY_LOOKING}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Should only get candidate1 (actively looking)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["work_status"], WorkStatus.ACTIVELY_LOOKING)

    def test_combined_filters(self):
        """Test multiple filters combined."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {
                "salary_min": 1000,
                "experience": 1,
                "search": "Developer"
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # All returned candidates should match all criteria
        for r in results:
            salary_value = int(r["current_salary"].replace(" ", ""))
            self.assertGreaterEqual(salary_value, 1000)

    def test_invalid_salary_filter_ignored(self):
        """Test that invalid salary values are ignored."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            {"salary_min": "invalid"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should still return results (filter ignored)
        results = response.data.get("data", response.data.get("results", response.data))
        self.assertGreater(len(results), 0)

    def test_response_includes_required_fields(self):
        """Test that response includes all required fields."""
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get("/api/v1/conversations/headhunting/candidates/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        self.assertGreater(len(results), 0)

        required_fields = [
            'resume_id', 'candidate_id', 'candidate_email', 'full_name',
            'position', 'work_status', 'total_experience'
        ]

        for field in required_fields:
            self.assertIn(field, results[0])

    def test_total_experience_format(self):
        """Test that total experience is formatted correctly in English."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(
            "/api/v1/conversations/headhunting/candidates/",
            HTTP_ACCEPT_LANGUAGE="en",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("data", response.data.get("results", response.data))

        # Find candidate1 with ~7 years experience (2016-01 to 2023-01 = 84 months = 7 years)
        candidate1_result = next(
            (r for r in results if r["candidate_email"] == "senior.dev@email.com"),
            None
        )
        self.assertIsNotNone(candidate1_result)
        self.assertEqual(candidate1_result["total_experience"], "7 years")

        # Find candidate2 with 1 year experience (2024-01 to 2025-01 = 12 months = 1 year)
        candidate2_result = next(
            (r for r in results if r["candidate_email"] == "junior.dev@email.com"),
            None
        )
        self.assertIsNotNone(candidate2_result)
        self.assertEqual(candidate2_result["total_experience"], "1 year")


class HeadhuntingInvitationViewTests(APITestCase):
    """Tests for HeadhuntingInvitationView."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

        # Create a company
        self.company = Company.objects.create(
            name="Hiring Corp",
            tin="111222333",
            is_active=True,
        )

        # Create a recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@hiringcorp.com",
            password="securepass123",
            is_recruiter=True,
            company=self.company,
        )

        # Create recruiter profile
        self.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Hiring Manager",
        )

        # Create subscription with headhunting access
        create_headhunting_subscription(self.company)

        # Create candidates
        self.candidate1 = Candidate.objects.create_user(
            email="candidate1@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate1_profile = CandidateProfile.objects.create(
            candidate=self.candidate1,
            full_name="Candidate One",
        )

        self.candidate2 = Candidate.objects.create_user(
            email="candidate2@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate2_profile = CandidateProfile.objects.create(
            candidate=self.candidate2,
            full_name="Candidate Two",
        )

        # Create a vacancy
        self.vacancy = Vacancy.objects.create(
            title="Python Developer",
            created_by=self.recruiter,
            company=self.company,
            is_active=True,
        )

        self.invitation_url = "/api/v1/conversations/headhunting/invite/"

    def test_send_invitation_requires_authentication(self):
        """Test that unauthenticated users cannot send invitations."""
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We would like to invite you for a position."
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_send_invitation_requires_recruiter_permission(self):
        """Test that only recruiters can send invitations."""
        self.client.force_authenticate(user=self.candidate1)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We would like to invite you for a position."
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_invitation_to_single_candidate(self):
        """Test sending invitation to a single candidate."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We are impressed by your profile and would like to discuss a position with you.",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["messages_sent"], 1)
        self.assertEqual(response.data["data"]["new_conversations"], 1)

        # Verify conversation was created
        self.assertTrue(
            Conversation.objects.filter(
                recruiter=self.recruiter,
                candidate=self.candidate1,
                application__isnull=True,
            ).exists()
        )

    def test_send_invitation_to_multiple_candidates(self):
        """Test sending invitation to multiple candidates."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id), str(self.candidate2.id)],
            "letter": "We have exciting opportunities for talented developers.",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["messages_sent"], 2)
        self.assertEqual(response.data["data"]["new_conversations"], 2)

    def test_send_invitation_to_existing_conversation(self):
        """Test sending invitation when conversation already exists."""
        # Create an existing headhunting conversation
        existing_conversation = Conversation.objects.create(
            application=None,
            candidate=self.candidate1,
            recruiter=self.recruiter,
            is_read_by_recruiter=True,
            is_read_by_candidate=True,
        )

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Following up on our previous conversation.",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["messages_sent"], 1)
        self.assertEqual(response.data["data"]["new_conversations"], 0)

        # Verify message was added to existing conversation
        existing_conversation.refresh_from_db()
        self.assertEqual(existing_conversation.messages.count(), 1)

        # Verify candidate is notified (marked as unread)
        self.assertFalse(existing_conversation.is_read_by_candidate)

    def test_send_invitation_with_nonexistent_candidate(self):
        """Test that nonexistent candidates are skipped."""
        import uuid
        fake_uuid = uuid.uuid4()

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id), str(fake_uuid)],
            "letter": "We have an opportunity for you."
        }, format='json')

        # Should fail validation because candidate doesn't exist
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invitation_letter_validation_min_length(self):
        """Test that letter must have minimum length."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Hi"  # Too short
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invitation_candidate_ids_max_limit(self):
        """Test that candidate_ids has a maximum limit of 50."""
        # Create 51 candidates
        candidates = []
        for i in range(51):
            c = Candidate.objects.create_user(
                email=f"bulk{i}@email.com",
                password="testpass123",
                is_candidate=True,
            )
            candidates.append(c)

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(c.id) for c in candidates],
            "letter": "We are reaching out to multiple candidates."
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invitation_with_inactive_vacancy_fails(self):
        """Test that inactive vacancy cannot be used for invitations."""
        # Create inactive vacancy
        inactive_vacancy = Vacancy.objects.create(
            title="Closed Position",
            created_by=self.recruiter,
            company=self.company,
            is_active=False,
        )

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We have a position for you.",
            "vacancy_id": str(inactive_vacancy.id)
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inactive", str(response.data).lower())

    def test_invitation_with_other_company_vacancy_fails(self):
        """Test that vacancy from another company cannot be used."""
        # Create another company and vacancy
        other_company = Company.objects.create(
            name="Other Corp",
            tin="999888777",
            is_active=True,
        )
        other_recruiter = Recruiter.objects.create_user(
            email="other@othercorp.com",
            password="testpass123",
            is_recruiter=True,
            company=other_company,
        )
        other_vacancy = Vacancy.objects.create(
            title="Other Position",
            created_by=other_recruiter,
            company=other_company,
            is_active=True,
        )

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We have a position for you.",
            "vacancy_id": str(other_vacancy.id)
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("company", str(response.data).lower())

    def test_invitation_creates_correct_message_type(self):
        """Test that invitation creates HUNTING_INVITATION message type."""
        from ..models import MessageType

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We would like to discuss an opportunity with you.",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify message type
        conversation = Conversation.objects.get(
            recruiter=self.recruiter,
            candidate=self.candidate1,
        )
        message = conversation.messages.first()
        self.assertEqual(message.message_type, MessageType.HUNTING_INVITATION)
        self.assertEqual(message.sender_type, "RECRUITER")
        self.assertFalse(message.is_read)

    def test_empty_candidate_ids_fails(self):
        """Test that empty candidate_ids list fails validation."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.post(self.invitation_url, {
            "candidate_ids": [],
            "letter": "We have an opportunity for you."
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class HeadhuntingVacancyMatchingTests(APITestCase):
    """Tests for vacancy matching functionality in HeadhuntingCandidateListView."""

    def setUp(self):
        """Set up test data for vacancy matching tests."""
        from apps.resumes.models import Resume
        from apps.resumes.models.choices import WorkStatus
        from decimal import Decimal
        import numpy as np

        self.client = APIClient()

        # Create a company
        self.company = Company.objects.create(
            name="Tech Corp",
            tin="987654321",
            is_active=True,
        )

        # Create another company for negative tests
        self.other_company = Company.objects.create(
            name="Other Corp",
            tin="111111111",
            is_active=True,
        )

        # Create a recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="hr@techcorp.com",
            password="securepass123",
            is_recruiter=True,
            company=self.company,
        )

        # Create recruiter for other company
        self.other_recruiter = Recruiter.objects.create_user(
            email="hr@othercorp.com",
            password="securepass123",
            is_recruiter=True,
            company=self.other_company,
        )

        # Create subscription with headhunting access
        create_headhunting_subscription(self.company)

        # Create vacancy with embedding
        self.vacancy = Vacancy.objects.create(
            title="Python Developer",
            created_by=self.recruiter,
            company=self.company,
            is_active=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),  # Random embedding for testing
        )

        # Create inactive vacancy
        self.inactive_vacancy = Vacancy.objects.create(
            title="Closed Position",
            created_by=self.recruiter,
            company=self.company,
            is_active=False,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

        # Create vacancy for other company
        self.other_vacancy = Vacancy.objects.create(
            title="Other Company Position",
            created_by=self.other_recruiter,
            company=self.other_company,
            is_active=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

        # Create candidate with embedded resume
        self.candidate1 = Candidate.objects.create_user(
            email="python.dev@email.com",
            password="testpass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=self.candidate1,
            full_name="Python Developer",
        )
        self.resume1 = Resume.objects.create(
            candidate=self.candidate1,
            title="Python Developer Resume",
            description="Experienced Python developer",
            position="Python Developer",
            work_status=WorkStatus.ACTIVELY_LOOKING,
            current_salary=Decimal("5000.00"),
            salary_currency="USD",
            is_active=True,
            is_main=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

        # Create another candidate
        self.candidate2 = Candidate.objects.create_user(
            email="java.dev@email.com",
            password="testpass123",
            is_candidate=True,
        )
        CandidateProfile.objects.create(
            candidate=self.candidate2,
            full_name="Java Developer",
        )
        self.resume2 = Resume.objects.create(
            candidate=self.candidate2,
            title="Java Developer Resume",
            description="Experienced Java developer",
            position="Java Developer",
            work_status=WorkStatus.OPEN_TO_OPPORTUNITIES,
            current_salary=Decimal("4500.00"),
            salary_currency="USD",
            is_active=True,
            is_main=True,
            is_embedded=True,
            embedding=np.random.rand(384).tolist(),
        )

        self.candidates_url = "/api/v1/conversations/headhunting/candidates/"

    def test_vacancy_matching_with_invalid_vacancy_id_returns_404(self):
        """Test that invalid vacancy_id returns 404."""
        import uuid

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.candidates_url, {
            "vacancy_id": str(uuid.uuid4()),
        })

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data.get("success", True))

    def test_vacancy_matching_with_other_company_vacancy_returns_403(self):
        """Test that using another company's vacancy returns 403."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.candidates_url, {
            "vacancy_id": str(self.other_vacancy.id),
        })

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data.get("success", True))
        self.assertIn("company", str(response.data).lower())

    def test_vacancy_matching_with_inactive_vacancy_returns_400(self):
        """Test that using inactive vacancy returns 400."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.candidates_url, {
            "vacancy_id": str(self.inactive_vacancy.id),
        })

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data.get("success", True))
        self.assertIn("inactive", str(response.data).lower())

    def test_vacancy_matching_without_vacancy_id_works(self):
        """Test that endpoint works without vacancy_id parameter."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.candidates_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return candidates (at least our 2 test candidates)
        results = response.data.get("data", response.data.get("results", response.data))
        self.assertGreaterEqual(len(results), 2)

    def test_vacancy_matching_preserves_existing_filters(self):
        """Test that vacancy matching works with existing filters."""
        from apps.resumes.models.choices import WorkStatus

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(self.candidates_url, {
            "vacancy_id": str(self.vacancy.id),
            "work_status": WorkStatus.ACTIVELY_LOOKING,
        })

        # Should succeed (even if matching returns no results due to mocked embeddings)
        self.assertIn(response.status_code, [status.HTTP_200_OK])


class HeadhuntingInvitationVariableRenderingTests(APITestCase):
    """Tests that template variables in invitation letters are rendered correctly."""

    def setUp(self):
        self.client = APIClient()

        self.company = Company.objects.create(
            name="Render Corp",
            tin="444555666",
            is_active=True,
        )

        self.recruiter = Recruiter.objects.create_user(
            email="render@rendercorp.com",
            password="securepass123",
            is_recruiter=True,
            company=self.company,
        )

        self.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Render Manager",
        )

        create_headhunting_subscription(self.company)

        self.candidate1 = Candidate.objects.create_user(
            email="alice@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate1_profile = CandidateProfile.objects.create(
            candidate=self.candidate1,
            full_name="Alice Johnson",
        )

        self.candidate2 = Candidate.objects.create_user(
            email="bob@email.com",
            password="testpass123",
            is_candidate=True,
        )
        self.candidate2_profile = CandidateProfile.objects.create(
            candidate=self.candidate2,
            full_name="Bob Smith",
        )

        self.candidate3 = Candidate.objects.create_user(
            email="noprofile@email.com",
            password="testpass123",
            is_candidate=True,
        )

        self.vacancy = Vacancy.objects.create(
            title="Frontend Developer",
            created_by=self.recruiter,
            company=self.company,
            is_active=True,
        )

        self.invitation_url = "/api/v1/conversations/headhunting/invite/"

    def test_invitation_renders_candidate_name_variable(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Hello {{candidate_name}}! We have an offer for you.",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.filter(
            conversation__candidate=self.candidate1,
        ).latest('created_at')
        self.assertIn("Hello Alice Johnson!", message.content)
        self.assertNotIn("{{candidate_name}}", message.content)

    def test_invitation_renders_position_variable(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "We are hiring for {{position}} position.",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.filter(
            conversation__candidate=self.candidate1,
        ).latest('created_at')
        self.assertIn("Frontend Developer", message.content)
        self.assertNotIn("{{position}}", message.content)

    def test_invitation_renders_company_name_variable(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Join {{company_name}} team!",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.filter(
            conversation__candidate=self.candidate1,
        ).latest('created_at')
        self.assertIn("Join Render Corp team!", message.content)
        self.assertNotIn("{{company_name}}", message.content)

    def test_each_candidate_gets_personalized_letter(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [
                str(self.candidate1.id),
                str(self.candidate2.id),
            ],
            "letter": "Dear {{candidate_name}}, welcome to {{company_name}}!",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        msg1 = Message.objects.filter(
            conversation__candidate=self.candidate1,
        ).latest('created_at')
        self.assertEqual(msg1.content, "Dear Alice Johnson, welcome to Render Corp!")

        msg2 = Message.objects.filter(
            conversation__candidate=self.candidate2,
        ).latest('created_at')
        self.assertEqual(msg2.content, "Dear Bob Smith, welcome to Render Corp!")

    def test_uzbek_variable_renders_in_message(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Salom {{nomzod_ismi}}, {{kompaniya_nomi}} ga xush kelibsiz!",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.filter(
            conversation__candidate=self.candidate1,
        ).latest('created_at')
        self.assertEqual(
            message.content,
            "Salom Alice Johnson, Render Corp ga xush kelibsiz!",
        )

    def test_unknown_variable_rejected_in_letter(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Hello {{bad_variable}}!",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fallback_to_email_when_no_candidate_full_name(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate3.id)],
            "letter": "Hello {{candidate_name}}, you are invited!",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.filter(
            conversation__candidate=self.candidate3,
        ).latest('created_at')
        self.assertIn("Hello [Candidate Name Not Set]", message.content)

    def test_variable_with_spaces_renders_in_letter(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.invitation_url, {
            "candidate_ids": [str(self.candidate1.id)],
            "letter": "Hello {{ candidate_name }}, welcome to {{   company_name   }}!",
            "vacancy_id": str(self.vacancy.id),
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        message = Message.objects.filter(
            conversation__candidate=self.candidate1,
        ).latest('created_at')
        self.assertEqual(
            message.content,
            "Hello Alice Johnson, welcome to Render Corp!",
        )
