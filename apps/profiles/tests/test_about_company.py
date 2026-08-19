from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.authentication.models import Company, Recruiter
from apps.domain.models import Domain
from apps.profiles.models import CompanyProfile, RecruiterProfile


class AboutCompanyAPITest(TestCase):
    """Test suite for About Company API"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create domain
        self.domain = Domain.objects.create(
            name="Information Technology",
            description="IT companies"
        )

        # Create company
        self.company = Company.objects.create(
            name="Test Tech Company",
            tin="123456789",
            domain=self.domain
        )

        # Create admin recruiter
        self.admin_recruiter = Recruiter.objects.create_user(
            email="admin@test.com",
            password="testpass123",
            company=self.company
        )
        self.admin_profile = RecruiterProfile.objects.create(
            recruiter=self.admin_recruiter,
            full_name="Admin User",
            level=RecruiterProfile.Level.ADMIN
        )

        # Create regular recruiter
        self.recruiter = Recruiter.objects.create_user(
            email="recruiter@test.com",
            password="testpass123",
            company=self.company
        )
        self.recruiter_profile = RecruiterProfile.objects.create(
            recruiter=self.recruiter,
            full_name="Recruiter User",
            level=RecruiterProfile.Level.RECRUITER
        )

        # Create manager-level recruiter (using RECRUITER level — MANAGER doesn't exist)
        self.manager_recruiter = Recruiter.objects.create_user(
            email="manager@test.com",
            password="testpass123",
            company=self.company,
        )
        RecruiterProfile.objects.create(
            recruiter=self.manager_recruiter,
            full_name="Manager User",
            level=RecruiterProfile.Level.RECRUITER,
        )

        # Create company profile
        self.company_profile = CompanyProfile.objects.create(
            company=self.company,
            description="<p>Test company description with <strong>HTML</strong></p>",
            address="123 Test Street",
            website="https://test.com"
        )

    def test_admin_can_view_company_info(self):
        """Test that admin recruiters can view company information"""
        self.client.force_authenticate(user=self.admin_recruiter)

        url = reverse('about-company-info')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company_name'], "Test Tech Company")
        self.assertEqual(response.data['company_domain'][0]['name'], "Information Technology")
        self.assertIn("<strong>HTML</strong>", response.data['description'])

    def test_recruiter_can_view_company_info(self):
        """Test that regular recruiters can view company information"""
        self.client.force_authenticate(user=self.recruiter)

        url = reverse('about-company-info')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company_name'], "Test Tech Company")

    def test_admin_can_update_company_info(self):
        """Test that admin recruiters can update company information"""
        self.client.force_authenticate(user=self.admin_recruiter)

        # Create new domain for testing domain change
        new_domain = Domain.objects.create(
            name="E-commerce",
            description="E-commerce companies"
        )

        url = reverse('about-company-info')
        data = {
            'description': '<p>Updated description with <em>new content</em></p>',
            'address': '456 Updated Street',
            'website': 'https://updated.com',
            'domain_id': new_domain.id
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], data['description'])
        self.assertEqual(response.data['address'], data['address'])
        self.assertEqual(response.data['website'], data['website'])
        self.assertEqual(response.data['company_domain'][0]['name'], "E-commerce")

        # Verify company domain was updated
        self.company.refresh_from_db()
        self.assertEqual(self.company.domain.name, "E-commerce")

    def test_manager_cannot_update_company_info(self):
        """Test that manager recruiters cannot update company information"""
        self.client.force_authenticate(user=self.manager_recruiter)

        url = reverse('about-company-info')
        data = {
            'description': 'Unauthorized update attempt',
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_recruiter_cannot_update_company_info(self):
        """Test that regular recruiters cannot update company information"""
        self.client.force_authenticate(user=self.recruiter)

        url = reverse('about-company-info')
        data = {
            'description': 'Unauthorized update attempt',
        }

        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_photo_upload_validation(self):
        """Test photo upload with size validation"""
        self.client.force_authenticate(user=self.admin_recruiter)

        # Create a small test image
        small_image = SimpleUploadedFile(
            "test.jpg",
            b"test image content",
            content_type="image/jpeg"
        )

        url = reverse('about-company-info')
        data = {
            'photo': small_image,
            'description': 'Test with photo upload'
        }

        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify photo was saved
        self.company_profile.refresh_from_db()
        self.assertTrue(self.company_profile.photo)

    def test_photo_upload_exceeds_max_size(self):
        """Test that photo upload exceeding 5MB is rejected"""
        from django.conf import settings
        from io import BytesIO
        from PIL import Image

        self.client.force_authenticate(user=self.admin_recruiter)

        # Create a valid image that exceeds 5MB
        # We'll create a large image by making it very large dimensions
        img = Image.new('RGB', (100, 100), color='red')
        buffer = BytesIO()
        img.save(buffer, format='JPEG')

        # Now create content larger than MAX_FILE_SIZE
        large_content = buffer.getvalue()
        # Pad to exceed 5MB
        padding_size = settings.MAX_FILE_SIZE + 1 - len(large_content)
        large_content = large_content + (b'\x00' * padding_size)

        large_image = SimpleUploadedFile(
            "large_test.jpg",
            large_content,
            content_type="image/jpeg"
        )

        url = reverse('about-company-info')
        data = {
            'photo': large_image,
        }

        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Check error is in field_errors (APIResponse format)
        self.assertIn('error', response.data)
        self.assertIn('field_errors', response.data['error'])
        self.assertIn('photo', response.data['error']['field_errors'])
        # Check error message contains size limit info
        error_message = str(response.data['error']['field_errors']['photo'])
        self.assertTrue(
            '5MB' in error_message or 'exceed' in error_message.lower(),
            f"Expected size limit in error message, got: {error_message}"
        )

    def test_website_url_validation(self):
        """Test website URL validation"""
        self.client.force_authenticate(user=self.admin_recruiter)

        url = reverse('about-company-info')

        # Test invalid URL (no protocol)
        data = {'website': 'invalid-url.com'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Website URL must start with http', response.data['error']['details'])

        # Test valid URL
        data = {'website': 'https://valid-url.com'}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_html_description_preserved(self):
        """Test that HTML content in description is preserved"""
        self.client.force_authenticate(user=self.admin_recruiter)

        url = reverse('about-company-info')
        html_content = '''
        <div>
            <h2>About Our Company</h2>
            <p>We are a <strong>leading technology</strong> company.</p>
            <ul>
                <li>Innovation</li>
                <li>Excellence</li>
            </ul>
        </div>
        '''

        data = {'description': html_content}
        response = self.client.patch(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], html_content)

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated users cannot access the API"""
        url = reverse('about-company-info')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class AboutCompanyPhotoTest(TestCase):
    """Test photo deletion in About Company API."""

    def setUp(self):
        self.client = APIClient()
        self.domain = Domain.objects.create(name="IT")
        self.company = Company.objects.create(name="Test Co", tin="123", domain=self.domain)
        self.admin = Recruiter.objects.create_user(email="admin@test.com", password="pwd", company=self.company)
        RecruiterProfile.objects.create(recruiter=self.admin, level=RecruiterProfile.Level.ADMIN)
        self.company_profile = CompanyProfile.objects.create(company=self.company)
        self.url = reverse('about-company-info')

    def test_delete_photo_success(self):
        self.client.force_authenticate(user=self.admin)
        image = SimpleUploadedFile("test.jpg", b"content", content_type="image/jpeg")
        self.company_profile.photo = image
        self.company_profile.save()

        response = self.client.patch(self.url, {"photo": None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.company_profile.refresh_from_db()
        self.assertFalse(self.company_profile.photo)

    def test_delete_photo_not_present(self):
        self.client.force_authenticate(user=self.admin)
        self.company_profile.photo = None
        self.company_profile.save()

        response = self.client.patch(self.url, {"photo": None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertIn('error', response.data)
        self.assertIn('field_errors', response.data['error'])
        self.assertIn('photo', response.data['error']['field_errors'])
        self.assertIn("Photo is not present.", str(response.data['error']['field_errors']['photo']))

    def test_auto_create_company_profile(self):
        """Test that company profile is automatically created if it doesn't exist"""
        # Create new company without profile
        new_company = Company.objects.create(
            name="New Company",
            tin="987654321"
        )

        new_recruiter = Recruiter.objects.create_user(
            email="new@test.com",
            password="testpass123",
            company=new_company
        )

        RecruiterProfile.objects.create(
            recruiter=new_recruiter,
            full_name="New Recruiter",
            level=RecruiterProfile.Level.ADMIN
        )

        self.client.force_authenticate(user=new_recruiter)

        url = reverse('about-company-info')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['company_name'], "New Company")

        # Verify profile was created
        self.assertTrue(
            CompanyProfile.objects.filter(company=new_company).exists()
        )
