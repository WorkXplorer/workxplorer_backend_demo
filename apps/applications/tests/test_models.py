"""
Unit tests for Applications models (JobApplication, ApplicationDocument).
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from datetime import timedelta, date

from apps.applications.models import JobApplication, ApplicationDocument
from apps.applications.models.choices import ApplicationStatus, ApplicationDocumentTypes
from apps.authentication.models import Candidate, Recruiter, Company
from apps.vacancies.models import Vacancy
from apps.resumes.models import Resume


class JobApplicationModelTests(TestCase):
    """Test suite for JobApplication model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123", company=cls.company
        )
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )
        cls.vacancy = Vacancy.objects.create(
            title="Software Engineer", company=cls.company, created_by=cls.recruiter
        )

    def test_create_job_application_successfully(self):
        """Test creating a job application with valid data."""
        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy
        )

        self.assertIsNotNone(application.id)
        self.assertEqual(application.candidate, self.candidate)
        self.assertEqual(application.vacancy, self.vacancy)
        self.assertEqual(application.status, ApplicationStatus.APPLIED)
        self.assertTrue(application.is_active)
        self.assertIsNotNone(application.applied_at)

    def test_job_application_string_representation(self):
        """Test the string representation of JobApplication."""
        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy
        )

        expected_str = f"{self.candidate} → {self.vacancy.title} (Applied)"
        self.assertEqual(str(application), expected_str)

    def test_unique_candidate_vacancy_constraint(self):
        """Test that a candidate can only apply once to each vacancy."""
        # Create the first application (this should succeed)
        JobApplication.objects.create(candidate=self.candidate, vacancy=self.vacancy)

        # Attempt to create a duplicate application (this should raise ValidationError)
        with self.assertRaises(ValidationError) as context:
            duplicate_application = JobApplication(
                candidate=self.candidate, vacancy=self.vacancy
            )
            duplicate_application.full_clean()  # Trigger validation manually
            duplicate_application.save()

        # Assert that the error message matches the unique constraint violation
        self.assertIn(
            "Job Application with this Candidate and Vacancy already exists.",
            str(context.exception),
        )

    def test_job_application_with_resume(self):
        """Test creating application with a resume."""
        resume = Resume.objects.create(candidate=self.candidate, title="My Resume")

        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy, resume_used=resume
        )

        self.assertEqual(application.resume_used, resume)

    def test_job_application_with_cover_letter(self):
        """Test creating application with a cover letter."""
        cover_letter = "I am very interested in this position..."

        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy, cover_letter=cover_letter
        )

        self.assertEqual(application.cover_letter, cover_letter)

    def test_job_application_ordering(self):
        """Test that applications are ordered by applied_at descending."""
        app1 = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy
        )

        # Create another vacancy for second application
        vacancy2 = Vacancy.objects.create(
            title="Backend Developer", company=self.company, created_by=self.recruiter
        )
        app2 = JobApplication.objects.create(candidate=self.candidate, vacancy=vacancy2)

        applications = JobApplication.objects.all()

        # Most recent first
        self.assertEqual(applications[0].id, app2.id)
        self.assertEqual(applications[1].id, app1.id)

    def test_days_since_application_property(self):
        """Test the days_since_application property."""
        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy
        )

        # Should be 0 days for just created application
        self.assertEqual(application.days_since_application, 0)

    def test_is_recent_property(self):
        """Test the is_recent property."""
        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy
        )

        # New application should be recent
        self.assertTrue(application.is_recent)

    def test_can_be_withdrawn_method(self):
        """Test the can_be_withdrawn method."""
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status=ApplicationStatus.APPLIED,
        )

        # APPLIED status can be withdrawn
        self.assertTrue(application.can_be_withdrawn())

        # OFFER_ACCEPTED status cannot be withdrawn
        application.status = ApplicationStatus.OFFER_ACCEPTED
        application.save()
        self.assertFalse(application.can_be_withdrawn())

    def test_can_be_reapplied_method(self):
        """Test the can_be_reapplied method."""
        application = JobApplication.objects.create(
            candidate=self.candidate,
            vacancy=self.vacancy,
            status=ApplicationStatus.APPLIED,
        )

        # APPLIED status cannot be reapplied
        self.assertFalse(application.can_be_reapplied())

        # WITHDRAWN status can be reapplied
        application.status = ApplicationStatus.WITHDRAWN
        application.save()
        self.assertTrue(application.can_be_reapplied())

    def test_advance_status_method(self):
        """Test the advance_status method."""
        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy
        )

        application.advance_status(
            ApplicationStatus.OFFERED,
            updated_by_recruiter=self.recruiter,
            notes="Candidate looks promising",
        )

        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.OFFERED)
        self.assertEqual(application.last_updated_by, self.recruiter)
        self.assertIn("Candidate looks promising", application.recruiter_notes)

    def test_validation_past_start_date(self):
        """Test validation for past start date."""
        past_date = date.today() - timedelta(days=10)

        application = JobApplication(
            candidate=self.candidate,
            vacancy=self.vacancy,
            earliest_start_date=past_date,
            status=ApplicationStatus.APPLIED,
        )

        with self.assertRaises(ValidationError):
            application.save()

    def test_additional_documents_json_field(self):
        """Test the additional_documents JSON field."""
        docs = {
            "certificate": "path/to/certificate.pdf",
            "portfolio": "https://myportfolio.com",
        }

        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy, additional_documents=docs
        )

        self.assertEqual(application.additional_documents, docs)

    def test_recruiter_notes_field(self):
        """Test the recruiter_notes field."""
        notes = "Excellent technical background. Strong communication skills."

        application = JobApplication.objects.create(
            candidate=self.candidate, vacancy=self.vacancy, recruiter_notes=notes
        )

        self.assertEqual(application.recruiter_notes, notes)


class ApplicationDocumentModelTests(TestCase):
    """Test suite for ApplicationDocument model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123", company=cls.company
        )
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )
        cls.vacancy = Vacancy.objects.create(
            title="Software Engineer", company=cls.company, created_by=cls.recruiter
        )
        cls.application = JobApplication.objects.create(
            candidate=cls.candidate, vacancy=cls.vacancy
        )

    def test_create_application_document_successfully(self):
        """Test creating an application document with valid data."""
        pdf_file = SimpleUploadedFile(
            "certificate.pdf", b"PDF content here", content_type="application/pdf"
        )

        document = ApplicationDocument.objects.create(
            application=self.application,
            document_type=ApplicationDocumentTypes.CERTIFICATE,
            title="My Certificate",
            file=pdf_file,
        )

        self.assertIsNotNone(document.id)
        self.assertEqual(document.application, self.application)
        self.assertEqual(document.document_type, ApplicationDocumentTypes.CERTIFICATE)
        self.assertEqual(document.title, "My Certificate")
        self.assertIsNotNone(document.created_at)

    def test_application_document_string_representation(self):
        """Test the string representation of ApplicationDocument."""
        pdf_file = SimpleUploadedFile(
            "portfolio.pdf", b"PDF content here", content_type="application/pdf"
        )

        document = ApplicationDocument.objects.create(
            application=self.application,
            document_type=ApplicationDocumentTypes.PORTFOLIO,
            title="My Portfolio",
            file=pdf_file,
        )

        expected_str = f"My Portfolio (Portfolio) - {self.application}"
        self.assertEqual(str(document), expected_str)

    def test_application_document_file_size_auto_populate(self):
        """Test that file size is auto-populated on save."""
        content = b"This is test content for file size"
        pdf_file = SimpleUploadedFile(
            "test.pdf", content, content_type="application/pdf"
        )

        document = ApplicationDocument.objects.create(
            application=self.application,
            document_type=ApplicationDocumentTypes.OTHER,
            title="Test Document",
            file=pdf_file,
        )

        self.assertIsNotNone(document.file_size)
        self.assertEqual(document.file_size, len(content))

    def test_application_document_ordering(self):
        """Test that documents are ordered by created_at descending."""
        pdf_file1 = SimpleUploadedFile(
            "doc1.pdf", b"Content 1", content_type="application/pdf"
        )
        pdf_file2 = SimpleUploadedFile(
            "doc2.pdf", b"Content 2", content_type="application/pdf"
        )

        doc1 = ApplicationDocument.objects.create(
            application=self.application, title="First Document", file=pdf_file1
        )
        doc2 = ApplicationDocument.objects.create(
            application=self.application, title="Second Document", file=pdf_file2
        )

        documents = ApplicationDocument.objects.all()

        # Most recent first
        self.assertEqual(documents[0].id, doc2.id)
        self.assertEqual(documents[1].id, doc1.id)

    def test_document_types(self):
        """Test different document types."""
        for doc_type, doc_label in ApplicationDocumentTypes.choices:
            pdf_file = SimpleUploadedFile(
                f"{doc_type}.pdf", b"Content", content_type="application/pdf"
            )

            document = ApplicationDocument.objects.create(
                application=self.application,
                document_type=doc_type,
                title=f"{doc_label} Document",
                file=pdf_file,
            )

            self.assertEqual(document.document_type, doc_type)
            self.assertEqual(document.get_document_type_display(), doc_label)
