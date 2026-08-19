from django.test import TestCase
from django.db.utils import IntegrityError
from apps.domain.models import HrCreatedProfession
from apps.authentication.models import Recruiter, Company
from apps.domain.models import Domain


class DomainModelTests(TestCase):
    """Test suite for Domain model."""

    def test_create_domain_successfully(self):
        """Test creating a domain with valid data."""
        domain = Domain.objects.create(
            name="Information Technology",
            description="IT and software development jobs",
        )

        self.assertEqual(domain.name, "Information Technology")
        self.assertEqual(domain.description, "IT and software development jobs")
        self.assertIsNotNone(domain.id)
        self.assertIsNotNone(domain.created_at)
        self.assertIsNotNone(domain.updated_at)

    def test_domain_string_representation(self):
        """Test the string representation of Domain."""
        domain = Domain.objects.create(name="Healthcare")

        self.assertEqual(str(domain), "Healthcare")

    def test_domain_name_uniqueness(self):
        """Test that domain names must be unique."""
        Domain.objects.create(name="Finance")

        with self.assertRaises(IntegrityError):
            Domain.objects.create(name="Finance")

    def test_domain_ordering(self):
        """Test that domains are ordered by name."""
        Domain.objects.create(name="Zebra Domain")
        Domain.objects.create(name="Apple Domain")
        Domain.objects.create(name="Banana Domain")

        domains = Domain.objects.all()

        self.assertEqual(domains[0].name, "Apple Domain")
        self.assertEqual(domains[1].name, "Banana Domain")
        self.assertEqual(domains[2].name, "Zebra Domain")

    def test_domain_with_empty_description(self):
        """Test creating a domain with empty description."""
        domain = Domain.objects.create(name="Marketing", description="")

        self.assertEqual(domain.name, "Marketing")
        self.assertEqual(domain.description, "")

    def test_domain_max_name_length(self):
        """Test domain name with maximum allowed length."""
        long_name = "A" * 255
        domain = Domain.objects.create(name=long_name)

        self.assertEqual(domain.name, long_name)
        self.assertEqual(len(domain.name), 255)

    def test_domain_update(self):
        """Test updating domain fields."""
        domain = Domain.objects.create(name="Sales", description="Original description")

        domain.description = "Updated description"
        domain.save()

        domain.refresh_from_db()
        self.assertEqual(domain.description, "Updated description")

    def test_domain_deletion(self):
        """Test deleting a domain."""
        domain = Domain.objects.create(name="Temporary Domain")
        domain_id = domain.id

        domain.delete()

        self.assertFalse(Domain.objects.filter(id=domain_id).exists())


class HrCreatedProfessionModelTest(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Test Company",
        )
        self.recruiter = Recruiter.objects.create(
            email="recruiter@test.com",
            company=self.company,
            is_recruiter=True,
        )
        self.hr_created_profession = HrCreatedProfession.objects.create(
            company=self.company,
            name="Test Profession",
            description="A test profession description",
            created_by=self.recruiter,
        )

    def test_hr_created_profession_creation(self):
        self.assertEqual(self.hr_created_profession.name, "Test Profession")
        self.assertEqual(self.hr_created_profession.company, self.company)
        self.assertEqual(self.hr_created_profession.created_by, self.recruiter)

    def test_hr_created_profession_str(self):
        self.assertEqual(str(self.hr_created_profession), "Test Profession")
