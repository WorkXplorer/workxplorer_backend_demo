from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from apps.authentication.models import Candidate, Recruiter, Company
from apps.profiles.models import CandidateProfile, RecruiterProfile
from apps.vacancies.models import Vacancy
from apps.applications.models import JobApplication
from ..models import Conversation, MessageType


class ConversationModelTests(TestCase):
    """Tests for Conversation and Message models."""

    def setUp(self):
        """Set up test data."""
        # Create a company
        self.company = Company.objects.create(
            name="Test Company",
            tin="123456789",
            is_active=True,
        )

        # Create a recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=self.company,
        )

        # Create recruiter profile
        self.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Test Recruiter",
        )

        # Create a candidate
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Create candidate profile
        self.candidate_profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test Candidate",
        )

        # Create a vacancy
        self.vacancy = Vacancy.objects.create(
            title="Software Developer",
            created_by=self.recruiter,
            company=self.company,
            is_active=True,
        )

    def test_conversation_created_on_application(self):
        """Test that conversation is automatically created when application is submitted."""
        # Create an application
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            cover_letter="This is my cover letter for the position.",
        )

        # Check that conversation was created
        self.assertTrue(
            Conversation.objects.filter(application=application).exists()
        )

        conversation = Conversation.objects.get(application=application)

        # Verify conversation participants
        self.assertEqual(conversation.candidate, self.candidate)
        self.assertEqual(conversation.recruiter, self.recruiter)

        # Verify cover letter message was created
        messages = conversation.messages.all()
        self.assertEqual(messages.count(), 1)

        message = messages.first()
        self.assertEqual(message.sender_type, "CANDIDATE")
        self.assertEqual(message.message_type, MessageType.COVER_LETTER)
        self.assertEqual(message.content, "This is my cover letter for the position.")

    def test_conversation_created_without_cover_letter(self):
        """Test conversation is created even without a cover letter, with a message from candidate."""
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            cover_letter="",
        )

        # Conversation should still be created
        self.assertTrue(
            Conversation.objects.filter(application=application).exists()
        )

        conversation = Conversation.objects.get(application=application)

        # A message from candidate should be created so the chat is not empty
        self.assertEqual(conversation.messages.count(), 1)
        message = conversation.messages.first()
        self.assertEqual(message.sender_type, "CANDIDATE")
        self.assertEqual(message.message_type, MessageType.TEXT)


class ConversationAPITests(APITestCase):
    """Tests for Conversation API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

        # Create a company
        self.company = Company.objects.create(
            name="Test Company",
            tin="123456789",
            is_active=True,
        )

        # Create a recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=self.company,
        )

        # Create recruiter profile
        self.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Test Recruiter",
        )

        # Create a candidate
        self.candidate = Candidate.objects.create_user(
            email="candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        # Create candidate profile
        self.candidate_profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test Candidate",
        )

        # Create a vacancy
        self.vacancy = Vacancy.objects.create(
            title="Software Developer",
            created_by=self.recruiter,
            company=self.company,
            is_active=True,
        )

        # Create an application (which triggers conversation creation)
        self.application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            cover_letter="Hello! I am applying for this position.",
        )

        # Get the created conversation
        self.conversation = Conversation.objects.get(application=self.application)

    def test_recruiter_can_list_conversations(self):
        """Test that recruiter can list their conversations."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get("/api/v1/conversations/recruiter/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and "results" in response.data:
            results = response.data["results"]
        else:
            results = response.data

        self.assertEqual(len(results), 1)
        self.assertEqual(
            str(results[0]["id"]),
            str(self.conversation.id)
        )

    def test_recruiter_can_view_conversation_detail(self):
        """Test that recruiter can view conversation details."""
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(
            f"/api/v1/conversations/recruiter/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.conversation.id))
        self.assertEqual(len(response.data["messages"]), 1)
        self.assertEqual(
            response.data["messages"][0]["content"],
            "Hello! I am applying for this position."
        )

    def test_recruiter_cannot_view_other_conversations(self):
        """Test that recruiter cannot view conversations they don't own."""
        # Create another recruiter
        other_recruiter = Recruiter.objects.create_user(
            email="other@test.com",
            password="testpass123",
            is_recruiter=True,
            company=self.company,
        )

        self.client.force_authenticate(user=other_recruiter)

        response = self.client.get(
            f"/api/v1/conversations/recruiter/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_candidate_can_list_conversations(self):
        """Test that candidate can list their conversations."""
        self.client.force_authenticate(user=self.candidate)

        response = self.client.get("/api/v1/conversations/candidate/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and "results" in response.data:
            results = response.data["results"]
        else:
            results = response.data

        self.assertEqual(len(results), 1)

    def test_candidate_can_view_conversation_detail(self):
        """Test that candidate can view their conversation."""
        self.client.force_authenticate(user=self.candidate)

        response = self.client.get(
            f"/api/v1/conversations/candidate/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["id"]), str(self.conversation.id))

    def test_candidate_cannot_view_other_conversations(self):
        """Test that candidate cannot view other conversations."""
        # Create another candidate
        other_candidate = Candidate.objects.create_user(
            email="other_candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        self.client.force_authenticate(user=other_candidate)

        response = self.client.get(
            f"/api/v1/conversations/candidate/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_viewing_marks_conversation_as_read(self):
        """Test that viewing a conversation marks it as read."""
        # Initially not read by recruiter
        self.assertFalse(self.conversation.is_read_by_recruiter)

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(
            f"/api/v1/conversations/recruiter/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh from database
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.is_read_by_recruiter)

    def test_candidate_viewing_marks_messages_as_read(self):
        """Test that candidate viewing a conversation marks recruiter messages as read."""
        from ..models import Message, MessageType

        # Create a message from recruiter that is unread
        recruiter_message = Message.objects.create(
            conversation=self.conversation,
            sender_type="RECRUITER",
            message_type=MessageType.TEXT,
            content="Hello, we reviewed your application.",
            is_read=False,
        )

        # Initially not read by candidate
        self.assertFalse(self.conversation.is_read_by_candidate)
        self.assertFalse(recruiter_message.is_read)

        self.client.force_authenticate(user=self.candidate)

        response = self.client.get(
            f"/api/v1/conversations/candidate/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh from database
        self.conversation.refresh_from_db()
        recruiter_message.refresh_from_db()

        self.assertTrue(self.conversation.is_read_by_candidate)
        self.assertTrue(recruiter_message.is_read)

    def test_recruiter_viewing_marks_candidate_messages_as_read(self):
        """Test that recruiter viewing a conversation marks candidate messages as read."""
        # The cover letter message from setUp should be marked as read

        # Initially not read by recruiter
        self.assertFalse(self.conversation.is_read_by_recruiter)

        self.client.force_authenticate(user=self.recruiter)

        response = self.client.get(
            f"/api/v1/conversations/recruiter/{self.conversation.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Refresh from database
        self.conversation.refresh_from_db()

        # Check that candidate messages are marked as read
        unread_candidate_messages = self.conversation.messages.filter(
            is_read=False,
            sender_type="CANDIDATE"
        ).count()
        self.assertEqual(unread_candidate_messages, 0)

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated users cannot access conversations."""
        response = self.client.get("/api/v1/conversations/recruiter/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.get("/api/v1/conversations/candidate/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
