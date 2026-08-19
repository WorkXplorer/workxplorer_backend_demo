from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError

from apps.general.models import EmailTemplate, Avatar


class EmailTemplateModelTests(TestCase):
    """Test suite for EmailTemplate model."""

    def test_create_email_template_successfully(self):
        """Test creating an email template with valid data."""
        # Create a simple HTML file
        html_content = b"<html><body>Hello {{name}}</body></html>"
        html_file = SimpleUploadedFile(
            "template.html", html_content, content_type="text/html"
        )

        template = EmailTemplate.objects.create(
            template_type="welcome",
            name="welcome-email",
            language="en",
            subject="Welcome to WorkXplorer",
            body=html_file,
        )

        self.assertEqual(template.name, "welcome-email")
        self.assertEqual(template.language, "en")
        self.assertEqual(template.subject, "Welcome to WorkXplorer")
        self.assertEqual(template.template_type, "welcome")

    def test_email_template_string_representation(self):
        """Test the string representation of EmailTemplate."""
        html_file = SimpleUploadedFile(
            "template.html", b"<html></html>", content_type="text/html"
        )

        template = EmailTemplate.objects.create(
            name="test-template", language="uz", subject="Test", body=html_file
        )

        self.assertEqual(str(template), "test-template (uz)")

    def test_email_template_unique_together(self):
        """Test that name and language combination must be unique."""
        html_file1 = SimpleUploadedFile(
            "template1.html", b"<html></html>", content_type="text/html"
        )
        html_file2 = SimpleUploadedFile(
            "template2.html", b"<html></html>", content_type="text/html"
        )

        EmailTemplate.objects.create(
            name="password-reset",
            language="en",
            subject="Reset Password",
            body=html_file1,
        )

        # Attempting to create another template with same name and language should fail
        with self.assertRaises(IntegrityError):
            EmailTemplate.objects.create(
                name="password-reset",
                language="en",
                subject="Reset Password 2",
                body=html_file2,
            )

    def test_email_template_different_languages(self):
        """Test creating templates with same name but different languages."""
        html_file_en = SimpleUploadedFile(
            "template_en.html",
            b"<html><body>English</body></html>",
            content_type="text/html",
        )
        html_file_uz = SimpleUploadedFile(
            "template_uz.html",
            b"<html><body>Uzbek</body></html>",
            content_type="text/html",
        )

        template_en = EmailTemplate.objects.create(
            name="notification",
            language="en",
            subject="Notification",
            body=html_file_en,
        )

        template_uz = EmailTemplate.objects.create(
            name="notification",
            language="uz",
            subject="Bildirishnoma",
            body=html_file_uz,
        )

        self.assertEqual(template_en.language, "en")
        self.assertEqual(template_uz.language, "uz")

    def test_email_template_language_choices(self):
        """Test email template language choices."""
        # Test with valid language
        for lang_code, lang_name in EmailTemplate.LANGUAGE_CHOICES:
            template = EmailTemplate.objects.create(
                name=f"test-{lang_code}",
                language=lang_code,
                subject=f"Subject {lang_code}",
                body=SimpleUploadedFile(
                    f"template_{lang_code}.html",
                    b"<html></html>",
                    content_type="text/html",
                ),
            )
            self.assertEqual(template.language, lang_code)


class AvatarModelTests(TestCase):
    """Test suite for Avatar model."""

    # Simple GIF image binary data for testing
    TEST_IMAGE_DATA = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x01\x44\x00\x3b"

    def test_create_avatar_successfully(self):
        """Test creating an avatar with valid data."""
        # Create a simple image file
        image_file = SimpleUploadedFile(
            "avatar.png", self.TEST_IMAGE_DATA, content_type="image/png"
        )

        avatar = Avatar.objects.create(image=image_file, is_active=True)

        self.assertIsNotNone(avatar.id)
        self.assertTrue(avatar.is_active)
        self.assertIsNotNone(avatar.created_at)
        self.assertIsNotNone(avatar.updated_at)

    def test_avatar_string_representation(self):
        """Test the string representation of Avatar."""
        image_file = SimpleUploadedFile(
            "avatar.png", self.TEST_IMAGE_DATA, content_type="image/png"
        )

        avatar = Avatar.objects.create(image=image_file)

        self.assertEqual(str(avatar), "Profile Avatar")

    def test_avatar_default_active_status(self):
        """Test that avatar is active by default."""
        image_file = SimpleUploadedFile(
            "avatar.png", self.TEST_IMAGE_DATA, content_type="image/png"
        )

        avatar = Avatar.objects.create(image=image_file)

        self.assertTrue(avatar.is_active)

    def test_avatar_inactive_status(self):
        """Test creating an inactive avatar."""
        image_file = SimpleUploadedFile(
            "avatar.png", self.TEST_IMAGE_DATA, content_type="image/png"
        )

        avatar = Avatar.objects.create(image=image_file, is_active=False)

        self.assertFalse(avatar.is_active)

    def test_avatar_update_active_status(self):
        """Test updating avatar active status."""
        image_file = SimpleUploadedFile(
            "avatar.png", self.TEST_IMAGE_DATA, content_type="image/png"
        )

        avatar = Avatar.objects.create(image=image_file, is_active=True)

        avatar.is_active = False
        avatar.save()

        avatar.refresh_from_db()
        self.assertFalse(avatar.is_active)

    def test_avatar_deletion(self):
        """Test deleting an avatar."""
        image_file = SimpleUploadedFile(
            "avatar.png", self.TEST_IMAGE_DATA, content_type="image/png"
        )

        avatar = Avatar.objects.create(image=image_file)
        avatar_id = avatar.id

        avatar.delete()

        self.assertFalse(Avatar.objects.filter(id=avatar_id).exists())
