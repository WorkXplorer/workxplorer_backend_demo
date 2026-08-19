from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.edupartners.models import EduPartnersType, EduPartner


class EduPartnersTypeModelTests(TestCase):
    """Test suite for EduPartnersType model."""

    def test_create_edupartners_type_successfully(self):
        """Test creating an educational partner type with valid data."""
        edu_type = EduPartnersType.objects.create(name="University")

        self.assertEqual(edu_type.name, "University")
        self.assertIsNotNone(edu_type.id)

    def test_edupartners_type_string_representation(self):
        """Test the string representation of EduPartnersType."""
        edu_type = EduPartnersType.objects.create(name="College")

        self.assertEqual(str(edu_type), "College")

    def test_edupartners_type_verbose_names(self):
        """Test EduPartnersType verbose names."""
        self.assertEqual(EduPartnersType._meta.verbose_name, "Educational Partner Type")
        self.assertEqual(
            EduPartnersType._meta.verbose_name_plural, "Educational Partner Types"
        )

    def test_multiple_edupartners_types(self):
        """Test creating multiple educational partner types."""
        types = ["University", "College", "School", "Institute"]

        for type_name in types:
            edu_type = EduPartnersType.objects.create(name=type_name)
            self.assertEqual(edu_type.name, type_name)

        self.assertEqual(EduPartnersType.objects.count(), 4)


class EduPartnerModelTests(TestCase):
    """Test suite for EduPartner model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.edu_type = EduPartnersType.objects.create(name="University")

    def test_create_edupartner_successfully(self):
        """Test creating an educational partner with valid data."""
        edupartner = EduPartner.objects.create(
            name="Tashkent State Technical University",
            edupartner_type=self.edu_type,
            country="Uzbekistan",
            city="Tashkent",
            website="https://www.tdtu.uz",
            description="Leading technical university in Uzbekistan",
        )

        self.assertEqual(edupartner.name, "Tashkent State Technical University")
        self.assertEqual(edupartner.edupartner_type, self.edu_type)
        self.assertEqual(edupartner.country, "Uzbekistan")
        self.assertEqual(edupartner.city, "Tashkent")
        self.assertEqual(edupartner.website, "https://www.tdtu.uz")
        self.assertTrue(edupartner.is_active)
        self.assertIsNotNone(edupartner.created_at)

    def test_edupartner_string_representation(self):
        """Test the string representation of EduPartner."""
        edupartner = EduPartner.objects.create(
            name="Test Institute",
            edupartner_type=self.edu_type,
            country="USA",
            city="New York",
        )

        expected_str = f"Test Institute - ({self.edu_type.name})"
        self.assertEqual(str(edupartner), expected_str)

    def test_edupartner_with_logo(self):
        """Test creating an educational partner with a logo."""
        # Create a simple image file
        image_content = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x01\x44\x00\x3b"
        logo_file = SimpleUploadedFile(
            "logo.png", image_content, content_type="image/png"
        )

        edupartner = EduPartner.objects.create(
            name="Logo Partner",
            edupartner_type=self.edu_type,
            country="UK",
            city="London",
            logo=logo_file,
        )

        self.assertIsNotNone(edupartner.logo)

    def test_edupartner_default_is_active(self):
        """Test that educational partner is active by default."""
        edupartner = EduPartner.objects.create(
            name="Default Active Partner",
            edupartner_type=self.edu_type,
            country="Canada",
            city="Toronto",
        )

        self.assertTrue(edupartner.is_active)

    def test_edupartner_inactive_status(self):
        """Test creating an inactive educational partner."""
        edupartner = EduPartner.objects.create(
            name="Inactive Partner",
            edupartner_type=self.edu_type,
            country="Australia",
            city="Sydney",
            is_active=False,
        )

        self.assertFalse(edupartner.is_active)

    def test_edupartner_with_empty_optional_fields(self):
        """Test creating an educational partner with empty optional fields."""
        edupartner = EduPartner.objects.create(
            name="Minimal Partner",
            edupartner_type=self.edu_type,
            country="Germany",
            city="Berlin",
        )

        self.assertEqual(edupartner.website, "")
        self.assertEqual(edupartner.description, "")
        self.assertFalse(edupartner.logo)

    def test_edupartner_ordering(self):
        """Test that educational partners are ordered by name."""
        EduPartner.objects.create(
            name="Zebra University",
            edupartner_type=self.edu_type,
            country="Country1",
            city="City1",
        )
        EduPartner.objects.create(
            name="Apple College",
            edupartner_type=self.edu_type,
            country="Country2",
            city="City2",
        )
        EduPartner.objects.create(
            name="Banana Institute",
            edupartner_type=self.edu_type,
            country="Country3",
            city="City3",
        )

        edupartners = EduPartner.objects.all()

        self.assertEqual(edupartners[0].name, "Apple College")
        self.assertEqual(edupartners[1].name, "Banana Institute")
        self.assertEqual(edupartners[2].name, "Zebra University")

    def test_edupartner_relationship_with_type(self):
        """Test the relationship between EduPartner and EduPartnersType."""
        college_type = EduPartnersType.objects.create(name="College")

        partner1 = EduPartner.objects.create(
            name="Partner 1", edupartner_type=college_type, country="USA", city="Boston"
        )
        partner2 = EduPartner.objects.create(
            name="Partner 2",
            edupartner_type=college_type,
            country="USA",
            city="Chicago",
        )

        # Both partners should have the same type
        self.assertEqual(partner1.edupartner_type, college_type)
        self.assertEqual(partner2.edupartner_type, college_type)

    def test_edupartner_deletion(self):
        """Test deleting an educational partner."""
        edupartner = EduPartner.objects.create(
            name="Temporary Partner",
            edupartner_type=self.edu_type,
            country="France",
            city="Paris",
        )
        edupartner_id = edupartner.id

        edupartner.delete()

        self.assertFalse(EduPartner.objects.filter(id=edupartner_id).exists())
