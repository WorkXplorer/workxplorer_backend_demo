from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.profiles.models import CandidateProfile, RecruiterProfile, CompanyProfile
from apps.authentication.models import Candidate, Recruiter, Company


class CandidateProfileModelTests(TestCase):
    """Test suite for CandidateProfile model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.candidate = Candidate.objects.create_user(
            email="candidate@test.com", password="testpass123"
        )

    def test_create_candidate_profile_successfully(self):
        """Test creating a candidate profile with valid data."""
        profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="John Doe",
            phone="+998901234567",
            candidate_email="john@example.com",
            address="Tashkent, Uzbekistan",
        )

        self.assertEqual(profile.candidate, self.candidate)
        self.assertEqual(profile.full_name, "John Doe")
        self.assertEqual(profile.phone, "+998901234567")
        self.assertEqual(profile.candidate_email, "john@example.com")
        self.assertEqual(profile.address, "Tashkent, Uzbekistan")

    def test_candidate_profile_string_representation(self):
        """Test the string representation of CandidateProfile."""
        profile = CandidateProfile.objects.create(
            candidate=self.candidate, full_name="Jane Smith"
        )

        self.assertEqual(str(profile), "Jane Smith")

    def test_candidate_profile_with_photo(self):
        """Test creating a candidate profile with a photo."""
        image_file = SimpleUploadedFile(
            "photo.jpg", b"image content", content_type="image/jpeg"
        )

        profile = CandidateProfile.objects.create(
            candidate=self.candidate, full_name="Photo Person", photo=image_file
        )

        self.assertIsNotNone(profile.photo)

    def test_candidate_profile_with_education_json(self):
        """Test storing education data in JSON field."""
        education_data = {
            "degree": "Bachelor's",
            "institution": "University of Tech",
            "year": 2020,
        }

        profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Educated Person",
            education=education_data,
        )

        self.assertEqual(profile.education, education_data)

    def test_candidate_profile_verbose_names(self):
        """Test CandidateProfile verbose names."""
        self.assertEqual(CandidateProfile._meta.verbose_name, "Candidate Profile")
        self.assertEqual(
            CandidateProfile._meta.verbose_name_plural, "Candidate Profiles"
        )

    def test_github_url_valid(self):
        """Test that valid GitHub URLs are accepted."""
        valid_urls = [
            "https://github.com/torvalds",
            "http://github.com/user123",
            "github.com/my-user",
            "github.com/user-name",
            "https://github.com/user123/",
        ]
        for url in valid_urls:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                github_url=url,
            )
            profile.full_clean()

    def test_github_url_invalid(self):
        """Test that invalid GitHub URLs are rejected."""
        invalid_urls = [
            "https://google.com",
            "github.com",
            "https://github.com/",
            "https://github.com/user name",
            "not-a-url",
            "ftp://github.com/user",
        ]
        for url in invalid_urls:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                github_url=url,
            )
            with self.assertRaises(Exception):
                profile.full_clean()

    def test_linkedin_url_valid(self):
        """Test that valid LinkedIn URLs are accepted."""
        valid_urls = [
            "https://linkedin.com/in/johndoe",
            "https://www.linkedin.com/in/jane-doe",
            "linkedin.com/in/user123",
            "https://linkedin.com/company/techcorp",
            "https://www.linkedin.com/company/my-company/",
        ]
        for url in valid_urls:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                linkedin_url=url,
            )
            profile.full_clean()

    def test_linkedin_url_invalid(self):
        """Test that invalid LinkedIn URLs are rejected."""
        invalid_urls = [
            "https://google.com",
            "linkedin.com",
            "https://linkedin.com/",
            "https://linkedin.com/jobs/view",
            "https://linkedin.com/profile/user",
        ]
        for url in invalid_urls:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                linkedin_url=url,
            )
            with self.assertRaises(Exception):
                profile.full_clean()

    def test_social_url_valid(self):
        """Test that valid portfolio/social URLs are accepted."""
        valid_urls = [
            "https://myportfolio.dev",
            "http://example.com",
            "www.mysite.com",
            "portfolio.io/projects",
            "https://sub.domain.co.uk/path?query=1",
            "behance.net/designer",
        ]
        for url in valid_urls:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                social_url=url,
            )
            profile.full_clean()

    def test_social_url_invalid(self):
        """Test that invalid social URLs are rejected."""
        invalid_urls = [
            "not-a-url",
            "justtext",
        ]
        for url in invalid_urls:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                social_url=url,
            )
            with self.assertRaises(Exception):
                profile.full_clean()

    def test_telegram_url_valid(self):
        """Test that valid Telegram URLs are accepted (canonical format only)."""
        valid_inputs = [
            "https://t.me/username",
            "https://t.me/my_user_name",
            "https://t.me/user123",
            "https://t.me/john_doe_123",
            "https://t.me/telegram_user",
            "https://t.me/a_very_long_telegram_username_x",
        ]
        for url in valid_inputs:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                telegram_url=url,
            )
            profile.full_clean()

    def test_telegram_url_invalid(self):
        """Test that invalid Telegram URLs are rejected."""
        invalid_inputs = [
            "https://google.com",
            "http://t.me/username",
            "t.me/username",
            "https://www.t.me/username",
            "@username",
            "username",
            "t.me/",
            "https://t.me/",
            "@",
            "ab",
            "abc",
            "abcd",
            "not-a-url",
            "https://t.me/user name",
            "@user name",
            "t.me/@username",
            "ftp://t.me/username",
        ]
        for url in invalid_inputs:
            profile = CandidateProfile(
                candidate=self.candidate,
                full_name="Test User",
                telegram_url=url,
            )
            with self.assertRaises(Exception):
                profile.full_clean()

    def test_telegram_url_null_blank_allowed(self):
        """Test that telegram_url field can be null/blank."""
        profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test User",
        )
        self.assertIsNone(profile.telegram_url)

    def test_telegram_url_stored_correctly(self):
        """Test that valid Telegram URLs are stored correctly."""
        profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test User",
            telegram_url="https://t.me/myuser123",
        )
        self.assertEqual(profile.telegram_url, "https://t.me/myuser123")

    def test_urls_null_blank_allowed(self):
        """Test that URL fields can be null/blank."""
        profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test User",
        )
        self.assertIsNone(profile.github_url)
        self.assertIsNone(profile.linkedin_url)
        self.assertIsNone(profile.social_url)
        self.assertIsNone(profile.telegram_url)

    def test_urls_stored_correctly(self):
        """Test that valid URLs are stored correctly."""
        profile = CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test User",
            github_url="https://github.com/myuser",
            linkedin_url="https://linkedin.com/in/myuser",
            social_url="https://myportfolio.dev",
            telegram_url="https://t.me/myuser123",
        )
        self.assertEqual(profile.github_url, "https://github.com/myuser")
        self.assertEqual(profile.linkedin_url, "https://linkedin.com/in/myuser")
        self.assertEqual(profile.social_url, "https://myportfolio.dev")
        self.assertEqual(profile.telegram_url, "https://t.me/myuser123")


class RecruiterProfileModelTests(TestCase):
    """Test suite for RecruiterProfile model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")
        cls.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com", password="testpass123", company=cls.company
        )

    def test_create_recruiter_profile_successfully(self):
        """Test creating a recruiter profile with valid data."""
        profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Alice Johnson",
            phone="+998901234567",
            level=RecruiterProfile.Level.RECRUITER,
        )

        self.assertEqual(profile.recruiter, self.recruiter)
        self.assertEqual(profile.full_name, "Alice Johnson")
        self.assertEqual(profile.phone, "+998901234567")
        self.assertEqual(profile.level, RecruiterProfile.Level.RECRUITER)

    def test_recruiter_profile_string_representation(self):
        """Test the string representation of RecruiterProfile."""
        profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter, full_name="Bob Manager"
        )

        self.assertEqual(str(profile), "Bob Manager")

    def test_recruiter_profile_levels(self):
        """Test different recruiter profile levels."""
        levels = [
            RecruiterProfile.Level.RECRUITER,
            RecruiterProfile.Level.ADMIN,
        ]

        for level in levels:
            recruiter = Recruiter.objects.create_user(
                email=f"{level}@test.com", password="testpass123"
            )
            profile = RecruiterProfile.objects.create(
                recruiter=recruiter, full_name=f"Person {level}", level=level
            )
            self.assertEqual(profile.level, level)

    def test_recruiter_profile_is_admin_property(self):
        """Test the is_admin property."""
        admin_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Admin User",
            level=RecruiterProfile.Level.ADMIN,
        )

        self.assertTrue(admin_profile.is_admin)

        recruiter_profile = RecruiterProfile.objects.create(
            recruiter=Recruiter.objects.create_user(
                email="another@test.com", password="testpass123"
            ),
            full_name="Regular User",
            level=RecruiterProfile.Level.RECRUITER,
        )

        self.assertFalse(recruiter_profile.is_admin)

    def test_recruiter_profile_with_photo(self):
        """Test creating a recruiter profile with a photo."""
        image_file = SimpleUploadedFile(
            "recruiter_photo.jpg", b"image content", content_type="image/jpeg"
        )

        profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter, full_name="Photo Recruiter", photo=image_file
        )

        self.assertIsNotNone(profile.photo)

    def test_recruiter_profile_ordering(self):
        """Test that recruiter profiles are ordered by full_name."""
        RecruiterProfile.objects.create(
            recruiter=self.recruiter, full_name="Zebra Person"
        )
        RecruiterProfile.objects.create(
            recruiter=Recruiter.objects.create_user(
                email="another@test.com", password="testpass123"
            ),
            full_name="Apple Person",
        )

        profiles = RecruiterProfile.objects.all()

        self.assertEqual(profiles[0].full_name, "Apple Person")
        self.assertEqual(profiles[1].full_name, "Zebra Person")

    def test_recruiter_profile_verbose_names(self):
        """Test RecruiterProfile verbose names."""
        self.assertEqual(RecruiterProfile._meta.verbose_name, "Recruiter Profile")
        self.assertEqual(
            RecruiterProfile._meta.verbose_name_plural, "Recruiter Profiles"
        )


class CompanyProfileModelTests(TestCase):
    """Test suite for CompanyProfile model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.company = Company.objects.create(name="Test Company", tin="123456789")

    def test_create_company_profile_successfully(self):
        """Test creating a company profile with valid data."""
        profile = CompanyProfile.objects.create(
            company=self.company,
            description="A leading tech company",
            address="123 Tech Street, Tashkent",
            website="https://www.company.com",
        )

        self.assertEqual(profile.company, self.company)
        self.assertEqual(profile.description, "A leading tech company")
        self.assertEqual(profile.address, "123 Tech Street, Tashkent")
        self.assertEqual(profile.website, "https://www.company.com")

    def test_company_profile_string_representation(self):
        """Test the string representation of CompanyProfile."""
        profile = CompanyProfile.objects.create(company=self.company)

        self.assertEqual(str(profile), self.company.name)

    def test_company_profile_with_photo(self):
        """Test creating a company profile with a photo."""
        image_file = SimpleUploadedFile(
            "company_logo.png", b"image content", content_type="image/png"
        )

        profile = CompanyProfile.objects.create(company=self.company, photo=image_file)

        self.assertIsNotNone(profile.photo)

    def test_company_profile_with_optional_fields_empty(self):
        """Test creating a company profile with empty optional fields."""
        profile = CompanyProfile.objects.create(company=self.company)

        self.assertIsNone(profile.description)
        self.assertIsNone(profile.address)
        self.assertIsNone(profile.website)

    def test_company_profile_verbose_names(self):
        """Test CompanyProfile verbose names."""
        self.assertEqual(CompanyProfile._meta.verbose_name, "Company Profile")
        self.assertEqual(CompanyProfile._meta.verbose_name_plural, "Company Profiles")

    def test_company_profile_relationship(self):
        """Test the relationship between Company and CompanyProfile."""
        profile = CompanyProfile.objects.create(
            company=self.company, description="Test description"
        )

        self.assertIn(profile, self.company.companyprofile.all())
