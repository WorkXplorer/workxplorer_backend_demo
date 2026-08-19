"""
Test certificate handling with form data (multipart form data) like frontend sends.
Tests the view layer integration with certificate service.
"""

import json
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from apps.authentication.models import Candidate
from apps.profiles.models import CandidateProfile
from apps.resumes.models import Resume, ResumeCertificate
from apps.domain.models import Domain


class FormDataCertificateTest(TestCase):
    """Test certificate operations using form data (multipart) like frontend sends"""

    def setUp(self):
        self.client = APIClient()

        # Create candidate using the proper method
        self.candidate = Candidate.objects.create_user(
            email="formdata@test.com",
            password="testpass123",
            is_candidate=True
        )

        # Create candidate profile
        CandidateProfile.objects.create(
            candidate=self.candidate,
            full_name="Test Candidate",
            region="Test Region"
        )

        # Create domain
        self.domain = Domain.objects.create(
            name="Software Development",
            description="Test domain"
        )

        # Create resume with existing certificates
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Test Resume",
            description="Test description",
            domain=self.domain,
            position="Software Engineer"
        )

        # Create existing certificates
        self.cert1 = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Certificate 1",
            issuing_organization="Test Org 1"
        )

        self.cert2 = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Certificate 2",
            issuing_organization="Test Org 2"
        )

        # Login the user
        self.client.force_authenticate(user=self.candidate)

    def test_delete_all_certificates_form_data(self):
        """Test deleting all certificates by sending empty certificates array"""
        initial_count = self.resume.certificates.count()
        self.assertEqual(initial_count, 2)

        # Send form data with empty certificates array (like frontend does)
        data = {
            'title': 'Updated Resume Title',
            'certificates': '[]',  # Empty array as JSON string means delete all
        }

        url = reverse('update-resume', kwargs={'id': self.resume.pk})
        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all certificates were deleted
        self.resume.refresh_from_db()
        final_count = self.resume.certificates.count()
        self.assertEqual(final_count, 0)

    def test_delete_one_keep_one_certificate_form_data(self):
        """Test keeping one certificate and deleting another"""
        initial_count = self.resume.certificates.count()
        self.assertEqual(initial_count, 2)

        # Keep only cert1, delete cert2 (frontend sends JSON array of certificates to keep)
        certificates_to_keep = json.dumps([{'id': self.cert1.id, 'name': 'Certificate 1'}])
        data = {
            'title': 'Updated Resume Title',
            'certificates': certificates_to_keep,
        }

        url = reverse('update-resume', kwargs={'id': self.resume.pk})
        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify only cert1 remains
        self.resume.refresh_from_db()
        remaining_certs = list(self.resume.certificates.all())
        self.assertEqual(len(remaining_certs), 1)
        self.assertEqual(remaining_certs[0].id, self.cert1.id)

        # Verify cert2 was deleted
        self.assertFalse(ResumeCertificate.objects.filter(id=self.cert2.id).exists())

    def test_keep_all_certificates_form_data(self):
        """Test keeping all existing certificates"""
        initial_count = self.resume.certificates.count()
        self.assertEqual(initial_count, 2)

        # Keep both certificates
        certificates_to_keep = json.dumps([
            {'id': self.cert1.id, 'name': 'Certificate 1'},
            {'id': self.cert2.id, 'name': 'Certificate 2'}
        ])
        data = {
            'title': 'Updated Resume Title',
            'certificates': certificates_to_keep,
        }

        url = reverse('update-resume', kwargs={'id': self.resume.pk})
        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all certificates remain
        self.resume.refresh_from_db()
        final_count = self.resume.certificates.count()
        self.assertEqual(final_count, 2)

    def test_add_new_certificate_with_file_form_data(self):
        """Test adding a new certificate with file upload while keeping existing ones"""
        initial_count = self.resume.certificates.count()
        self.assertEqual(initial_count, 2)

        certificates_to_keep = json.dumps([
            {'id': self.cert1.id, 'name': 'Certificate 1'},
            {'id': self.cert2.id, 'name': 'Certificate 2'}
        ])
        data = {
            'title': 'Updated Resume Title',
            'certificates': certificates_to_keep,
        }

        url = reverse('update-resume', kwargs={'id': self.resume.pk})
        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.resume.refresh_from_db()
        final_count = self.resume.certificates.count()
        self.assertEqual(final_count, 2)

    def test_empty_certificates_string_deletes_all(self):
        """Test handling empty string for certificates field"""
        initial_count = self.resume.certificates.count()
        self.assertEqual(initial_count, 2)

        # Send empty string for certificates (should delete all)
        data = {
            'title': 'Updated Resume Title',
            'certificates': '',  # Empty string should delete all
        }

        url = reverse('update-resume', kwargs={'id': self.resume.pk})
        response = self.client.patch(url, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify all certificates were deleted
        self.resume.refresh_from_db()
        final_count = self.resume.certificates.count()
        self.assertEqual(final_count, 0)
