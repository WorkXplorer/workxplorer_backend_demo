from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.hr_templates.models import Template
from apps.authentication.models import Candidate
from apps.authentication.models.recruiter import Company, Recruiter
from apps.profiles.models import RecruiterProfile
from apps.vacancies.models import Vacancy
from apps.applications.models.applications import JobApplication
from apps.applications.models.choices import ApplicationStatus


class RecruiterNotesOnStatusChangeTests(APITestCase):
    """
    Verify that recruiter_notes can be sent along with status changes
    on job applications. This tests the integration between the Template
    model (hr_templates) and the application status update flow.

    Template values are sent as plain text in recruiter_notes
    from the frontend, so we verify that:
    1. recruiter_notes are accepted when status changes
    2. Template text works as recruiter_notes
    3. Notes are properly persisted in the audit trail
    4. Status can change with or without notes
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Notes Test Company", tin="300000001")

        cls.recruiter = Recruiter.objects.create_user(
            email="notes_recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Notes Recruiter",
            level="Admin",
        )

        cls.candidate = Candidate.objects.create_user(
            email="notes_candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )

        cls.vacancy = Vacancy.objects.create(
            title="Notes Test Vacancy",
            company=cls.company,
            created_by=cls.recruiter,
        )

        # Create templates to simulate values from hr_templates
        cls.rejection_template = Template.objects.create(
            title="Insufficient experience",
            description="The candidate does not meet the minimum years of experience required for this role.",
            company=cls.company,
            template_type=Template.TemplateType.INVITATION,
        )
        cls.hold_template = Template.objects.create(
            title="Budget review",
            description="Position is on hold pending budget approval for the next quarter.",
            company=cls.company,
            template_type=Template.TemplateType.INVITATION,
        )

    def _create_application(self, initial_status=ApplicationStatus.APPLIED):
        """Helper to create a fresh application for each test."""
        return JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            applied_at=timezone.now(),
            status=initial_status,
        )

    def _get_update_url(self, application_id):
        return reverse(
            "update-application-status",
            kwargs={"application_id": application_id},
        )

    def test_status_change_with_recruiter_notes(self):
        """
        Status change with recruiter_notes should succeed and persist the notes.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": "Candidate did not pass technical screening.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn(
            "Candidate did not pass technical screening.",
            application.recruiter_notes,
        )
        self.assertEqual(application.status, ApplicationStatus.REJECTED)

    def test_status_change_with_template_text(self):
        """
        Using the text from a Reason template as recruiter_notes should work.
        This simulates the frontend sending the Reason.description as recruiter_notes.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        # Use the rejection reason's description as the notes (like the frontend would)
        reason_text = self.rejection_template.description
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": reason_text,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn(reason_text, application.recruiter_notes)

    def test_status_change_with_template_title_as_notes(self):
        """
        Using the Reason.title as recruiter_notes should also work.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": self.rejection_template.title,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn(self.rejection_template.title, application.recruiter_notes)

    def test_status_change_without_notes_succeeds(self):
        """
        Status change without recruiter_notes should still succeed.
        Notes are optional.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.patch(
            self._get_update_url(application.id),
            {"status": ApplicationStatus.INTERVIEW_SCHEDULED},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.INTERVIEW_SCHEDULED)

    def test_notes_without_status_change(self):
        """
        Sending recruiter_notes without changing status should also work.
        This allows adding notes to applications without altering the status.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.patch(
            self._get_update_url(application.id),
            {"recruiter_notes": "Adding supplementary notes about the candidate."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn(
            "Adding supplementary notes about the candidate.",
            application.recruiter_notes,
        )

    def test_notes_audit_trail_includes_timestamp(self):
        """
        When status changes with notes, the audit trail should include
        a timestamp in the recruiter_notes.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": self.hold_template.description,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        # The view adds timestamps to notes during status changes
        self.assertIn("Status changed from", application.recruiter_notes)
        self.assertIn(self.hold_template.description, application.recruiter_notes)

    def test_multiple_status_changes_append_notes(self):
        """
        Multiple status changes should append notes, building an audit trail.
        """
        application = self._create_application(initial_status=ApplicationStatus.APPLIED)
        self.client.force_authenticate(user=self.recruiter)

        # First status change: APPLIED → INTERVIEW_SCHEDULED
        self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.INTERVIEW_SCHEDULED,
                "recruiter_notes": "Moving to interview stage.",
            },
            format="json",
        )

        # Second status change: INTERVIEW_SCHEDULED → REJECTED
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": self.rejection_template.description,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        # Both notes should be in the audit trail
        self.assertIn("Moving to interview stage.", application.recruiter_notes)
        self.assertIn(
            self.rejection_template.description, application.recruiter_notes
        )

    def test_long_template_description_as_notes(self):
        """
        Long reason description text should be accepted as recruiter_notes.
        """
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)

        long_text = (
            "After careful consideration of the candidate's qualifications, "
            "work experience, and interview performance, we have decided to "
            "proceed with other candidates who more closely match the specific "
            "technical requirements outlined in the job description. "
            "We appreciate the time and effort invested in the application process."
        )
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": long_text,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn(long_text, application.recruiter_notes)


class StatusChangeVariableRenderingTests(APITestCase):
    """
    Tests that template variables in recruiter_notes are rendered
    correctly during status changes.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Render Status Corp", tin="500000001")

        cls.recruiter = Recruiter.objects.create_user(
            email="render_status_recruiter@test.com",
            password="testpass123",
            is_recruiter=True,
            company=cls.company,
        )
        RecruiterProfile.objects.create(
            recruiter=cls.recruiter,
            full_name="Render Status Recruiter",
            level="Admin",
        )

        cls.candidate = Candidate.objects.create_user(
            email="render_status_candidate@test.com",
            password="testpass123",
            is_candidate=True,
        )
        from apps.profiles.models import CandidateProfile
        cls.candidate_profile = CandidateProfile.objects.create(
            candidate=cls.candidate,
            full_name="Aliya Karimova",
        )

        cls.vacancy = Vacancy.objects.create(
            title="Data Analyst",
            company=cls.company,
            created_by=cls.recruiter,
        )

    def _create_application(self):
        return JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            applied_at=timezone.now(),
            status=ApplicationStatus.APPLIED,
        )

    def _get_update_url(self, application_id):
        return reverse(
            "update-application-status",
            kwargs={"application_id": application_id},
        )

    def test_candidate_name_variable_rendered(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": "Dear {{candidate_name}}, we regret to inform you.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Dear Aliya Karimova", application.recruiter_notes)
        self.assertNotIn("{{candidate_name}}", application.recruiter_notes)

    def test_position_variable_rendered(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.INTERVIEW_SCHEDULED,
                "recruiter_notes": "You are invited for {{position}} interview.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Data Analyst", application.recruiter_notes)
        self.assertNotIn("{{position}}", application.recruiter_notes)

    def test_company_name_variable_rendered(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": "Thank you for applying to {{company_name}}.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Render Status Corp", application.recruiter_notes)
        self.assertNotIn("{{company_name}}", application.recruiter_notes)

    def test_uzbek_variable_rendered(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": "Hurmatli {{nomzod_ismi}}, arizangiz ko'rib chiqildi.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Hurmatli Aliya Karimova", application.recruiter_notes)
        self.assertNotIn("{{nomzod_ismi}}", application.recruiter_notes)

    def test_unknown_variable_rejected(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": "Hello {{bad_variable}}!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_all_variables_rendered(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        text = "{{candidate_name}}, {{position}}, {{company_name}}"
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.REJECTED,
                "recruiter_notes": text,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Aliya Karimova, Data Analyst, Render Status Corp", application.recruiter_notes)

    def test_empty_notes_skips_rendering(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.INTERVIEW_SCHEDULED,
                "recruiter_notes": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertEqual(application.recruiter_notes, "")

    def test_rendering_works_without_candidate_profile(self):
        from apps.profiles.models import CandidateProfile
        CandidateProfile.objects.filter(candidate=self.candidate).delete()
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.INTERVIEW_SCHEDULED,
                "recruiter_notes": "Thanks {{candidate_name}} for applying.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Thanks [Candidate Name Not Set]", application.recruiter_notes)

    def test_variable_with_spaces_is_rendered(self):
        application = self._create_application()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            self._get_update_url(application.id),
            {
                "status": ApplicationStatus.INTERVIEW_SCHEDULED,
                "recruiter_notes": "Dear {{ candidate_name }}, welcome.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        self.assertIn("Dear Aliya Karimova", application.recruiter_notes)
        self.assertNotIn("{{ candidate_name }}", application.recruiter_notes)
