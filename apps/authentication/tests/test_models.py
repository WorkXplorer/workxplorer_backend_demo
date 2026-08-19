from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.authentication.models import CustomUser, Candidate, Recruiter, Company


class CustomUserModelTests(TestCase):
    """Test suite for CustomUser model."""

    def test_create_user_successfully(self):
        """Test creating a user with valid data."""
        user = CustomUser.objects.create_user(
            email="user@test.com", password="testpass123"
        )

        self.assertEqual(user.email, "user@test.com")
        self.assertTrue(user.check_password("testpass123"))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_candidate)
        self.assertFalse(user.is_recruiter)
        self.assertIsNotNone(user.date_joined)

    def test_create_superuser_successfully(self):
        """Test creating a superuser."""
        superuser = CustomUser.objects.create_superuser(
            email="admin@test.com", password="adminpass123"
        )

        self.assertEqual(superuser.email, "admin@test.com")
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_active)

    def test_user_string_representation(self):
        """Test the string representation of CustomUser."""
        user = CustomUser.objects.create_user(
            email="test@example.com", password="testpass123"
        )

        self.assertEqual(str(user), "test@example.com")

    def test_user_email_uniqueness(self):
        """Test that user emails must be unique."""
        CustomUser.objects.create_user(email="unique@test.com", password="testpass123")

        with self.assertRaises(IntegrityError):
            CustomUser.objects.create_user(
                email="unique@test.com", password="anotherpass"
            )

    def test_user_email_normalization(self):
        """Test that email is normalized."""
        user = CustomUser.objects.create_user(
            email="Test@EXAMPLE.COM", password="testpass123"
        )

        self.assertEqual(user.email, "Test@example.com")

    def test_create_user_without_email_raises_error(self):
        """Test that creating user without email raises ValueError."""
        with self.assertRaises(ValueError) as context:
            CustomUser.objects.create_user(email="", password="testpass123")

        self.assertIn("The Email field must be set", str(context.exception))

    def test_user_inactive_status(self):
        """Test creating an inactive user."""
        user = CustomUser.objects.create_user(
            email="inactive@test.com", password="testpass123", is_active=False
        )

        self.assertFalse(user.is_active)

    def test_user_candidate_flag(self):
        """Test setting is_candidate flag."""
        user = CustomUser.objects.create_user(
            email="candidate@test.com", password="testpass123", is_candidate=True
        )

        self.assertTrue(user.is_candidate)
        self.assertFalse(user.is_recruiter)

    def test_user_recruiter_flag(self):
        """Test setting is_recruiter flag."""
        user = CustomUser.objects.create_user(
            email="recruiter@test.com", password="testpass123", is_recruiter=True
        )

        self.assertTrue(user.is_recruiter)
        self.assertFalse(user.is_candidate)


class CandidateModelTests(TestCase):
    """Test suite for Candidate model."""

    def test_create_candidate_successfully(self):
        """Test creating a candidate."""
        candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )

        self.assertEqual(candidate.email, "candidate@test.com")
        self.assertTrue(candidate.is_candidate)
        self.assertFalse(candidate.is_recruiter)
        self.assertTrue(candidate.is_active)

    def test_candidate_auto_sets_is_candidate_flag(self):
        """Test that creating a Candidate automatically sets is_candidate to True."""
        candidate = Candidate.objects.create_user(
            email="auto@test.com", password="testpass123"
        )

        self.assertTrue(candidate.is_candidate)

    def test_candidate_inherits_from_custom_user(self):
        """Test that Candidate inherits from CustomUser."""
        candidate = Candidate.objects.create_user(
            email="inherit@test.com", password="testpass123"
        )

        self.assertIsInstance(candidate, CustomUser)

    def test_candidate_verbose_names(self):
        """Test Candidate model verbose names."""
        self.assertEqual(Candidate._meta.verbose_name, "Candidate")
        self.assertEqual(Candidate._meta.verbose_name_plural, "Candidates")


class CompanyModelTests(TestCase):
    """Test suite for Company model."""

    def test_create_company_successfully(self):
        """Test creating a company with valid data."""
        company = Company.objects.create(name="Tech Corp", tin="123456789")

        self.assertEqual(company.name, "Tech Corp")
        self.assertEqual(company.tin, "123456789")
        self.assertFalse(company.is_active)
        self.assertIsNotNone(company.id)

    def test_company_string_representation(self):
        """Test the string representation of Company."""
        company = Company.objects.create(name="Test Company", tin="987654321")

        self.assertEqual(str(company), "Test Company")

    def test_company_tin_uniqueness(self):
        """Test that company TIN must be unique."""
        Company.objects.create(name="Company One", tin="111111111")

        with self.assertRaises(IntegrityError):
            Company.objects.create(name="Company Two", tin="111111111")

    def test_company_with_domain(self):
        """Test creating a company with domain."""
        from apps.domain.models import Domain

        # Create a domain first
        domain = Domain.objects.create(
            name="Technology",
            description="Technology companies"
        )

        company = Company.objects.create(
            name="Startup Inc", tin="222222222", domain=domain
        )

        self.assertEqual(company.domain.name, "Technology")

    def test_company_with_file(self):
        """Test creating a company with a file."""
        pdf_file = SimpleUploadedFile(
            "company_doc.pdf", b"PDF content", content_type="application/pdf"
        )

        company = Company.objects.create(
            name="File Company", tin="333333333", file=pdf_file
        )

        self.assertIsNotNone(company.file)

    def test_company_active_status(self):
        """Test setting company as active."""
        company = Company.objects.create(
            name="Active Company", tin="444444444", is_active=True
        )

        self.assertTrue(company.is_active)

    def test_company_verbose_names(self):
        """Test Company model verbose names."""
        self.assertEqual(Company._meta.verbose_name, "Company")
        self.assertEqual(Company._meta.verbose_name_plural, "Companies")


class RecruiterModelTests(TestCase):
    """Test suite for Recruiter model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")

    def test_create_recruiter_successfully(self):
        """Test creating a recruiter."""
        recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123", company=self.company
        )

        self.assertEqual(recruiter.email, "recruiter@test.com")
        self.assertTrue(recruiter.is_recruiter)
        self.assertFalse(recruiter.is_candidate)
        self.assertEqual(recruiter.company, self.company)
        self.assertFalse(recruiter.is_waiting_approval)

    def test_recruiter_auto_sets_is_recruiter_flag(self):
        """Test that creating a Recruiter automatically sets is_recruiter to True."""
        recruiter = Recruiter.objects.create_user(
            email="auto@test.com", password="testpass123"
        )

        self.assertTrue(recruiter.is_recruiter)

    def test_recruiter_without_company(self):
        """Test creating a recruiter without a company."""
        recruiter = Recruiter.objects.create_user(
            email="nocompany@test.com", password="testpass123"
        )

        self.assertIsNone(recruiter.company)

    def test_recruiter_waiting_approval_flag(self):
        """Test the is_waiting_approval flag."""
        recruiter = Recruiter.objects.create_user(
            email="waiting@test.com", password="testpass123", is_waiting_approval=True
        )

        self.assertTrue(recruiter.is_waiting_approval)

    def test_recruiter_inherits_from_custom_user(self):
        """Test that Recruiter inherits from CustomUser."""
        recruiter = Recruiter.objects.create_user(
            email="inherit@test.com", password="testpass123"
        )

        self.assertIsInstance(recruiter, CustomUser)

    def test_recruiter_verbose_names(self):
        """Test Recruiter model verbose names."""
        self.assertEqual(Recruiter._meta.verbose_name, "Recruiter")
        self.assertEqual(Recruiter._meta.verbose_name_plural, "Recruiters")

    def test_company_recruiter_relationship(self):
        """Test the relationship between Company and Recruiter."""
        recruiter = Recruiter.objects.create_user(
            email="relation@test.com", password="testpass123", company=self.company
        )

        self.assertIn(recruiter, self.company.recruiters.all())
