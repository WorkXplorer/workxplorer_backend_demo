"""
Test cases for certificate management functionality in resumes.
Tests certificate deletion, file cleanup, and update optimization.
"""

from unittest.mock import patch
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from rest_framework.test import APITestCase
from apps.authentication.models import Candidate
from apps.resumes.models import Resume, ResumeCertificate
from apps.resumes.services import CertificateService
from apps.resumes.serializers import ResumeSerializer


class CertificateServiceTest(TestCase):
    """Test the CertificateService functionality."""

    def setUp(self):
        """Set up test data."""
        self.candidate = Candidate.objects.create(
            email="test@example.com",
            password="testpass123",
            is_candidate=True
        )
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Test Resume",
            description="Test description",
            position="Software Developer"
        )

    def test_clean_certificate_file_success(self):
        """Test successful file cleanup."""
        # Create a temporary file
        test_file = SimpleUploadedFile("test.pdf", b"test content", content_type="application/pdf")

        certificate = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Test Certificate",
            file=test_file
        )

        # Mock the storage to simulate file existence
        with patch.object(default_storage, 'exists', return_value=True), \
                patch.object(default_storage, 'delete') as mock_delete:
            CertificateService.clean_certificate_file(certificate)
            mock_delete.assert_called_once_with(certificate.file.name)

    def test_clean_certificate_file_no_file(self):
        """Test file cleanup when no file exists."""
        certificate = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Test Certificate Without File"
        )

        # Should not raise an exception
        CertificateService.clean_certificate_file(certificate)

    def test_delete_certificates_with_files(self):
        """Test deleting certificates with file cleanup."""
        # Create certificates with files
        test_file1 = SimpleUploadedFile("test1.pdf", b"content1", content_type="application/pdf")
        test_file2 = SimpleUploadedFile("test2.pdf", b"content2", content_type="application/pdf")

        ResumeCertificate.objects.create(
            resume=self.resume,
            name="Certificate 1",
            file=test_file1
        )
        ResumeCertificate.objects.create(
            resume=self.resume,
            name="Certificate 2",
            file=test_file2
        )

        # Mock file operations
        with patch.object(default_storage, 'exists', return_value=True), \
                patch.object(default_storage, 'delete') as mock_delete:
            # Delete all certificates
            CertificateService.delete_certificates(self.resume.certificates)

            # Verify files were deleted
            self.assertEqual(mock_delete.call_count, 2)

            # Verify database records were deleted
            self.assertEqual(ResumeCertificate.objects.filter(resume=self.resume).count(), 0)

    def test_validate_certificates_data_with_ids(self):
        """Test certificate validation with existing IDs."""
        # Create existing certificates
        cert1 = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Existing Certificate 1"
        )
        cert2 = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Existing Certificate 2"
        )

        certificates_data = [
            {
                "id": cert1.id,
                "name": "Updated Certificate 1",
                "issuing_organization": "Test Org"
            },
            {
                # New certificate without ID
                "name": "New Certificate",
                "issuing_organization": "New Org"
            }
        ]

        validated_certificates, to_delete_ids = CertificateService.validate_certificates_data(
            certificates_data, self.resume
        )

        # Should have validated all certificates
        self.assertEqual(len(validated_certificates), 2)

        # cert2 should be marked for deletion (not in the update data)
        self.assertIn(cert2.id, to_delete_ids)
        self.assertNotIn(cert1.id, to_delete_ids)

    def test_validate_certificates_data_invalid_id(self):
        """Test validation fails for invalid certificate ID."""
        from rest_framework import serializers

        certificates_data = [
            {
                "id": 99999,  # Non-existent ID
                "name": "Invalid Certificate"
            }
        ]

        with self.assertRaises(serializers.ValidationError):
            CertificateService.validate_certificates_data(certificates_data, self.resume)

    def test_update_resume_certificates_optimization(self):
        """Test that update only modifies changed certificates."""
        # Create existing certificates
        cert1 = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Certificate 1",
            issuing_organization="Org 1"
        )
        cert2 = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Certificate 2",
            issuing_organization="Org 2"
        )

        certificates_data = [
            {
                "id": cert1.id,
                "name": "Updated Certificate 1",
                "issuing_organization": "Updated Org 1"
            },
            {
                # New certificate
                "name": "New Certificate",
                "issuing_organization": "New Org"
            }
        ]

        # Mock file operations for cert2 deletion
        with patch.object(default_storage, 'exists', return_value=False), \
                patch.object(default_storage, 'delete') as mock_delete:
            CertificateService.update_resume_certificates(self.resume, certificates_data)

            # Verify cert1 was updated
            cert1.refresh_from_db()
            self.assertEqual(cert1.name, "Updated Certificate 1")
            self.assertEqual(cert1.issuing_organization, "Updated Org 1")

            # Verify cert2 was deleted
            with self.assertRaises(ResumeCertificate.DoesNotExist):
                cert2.refresh_from_db()

            # Verify new certificate was created
            new_certificates = ResumeCertificate.objects.filter(
                resume=self.resume,
                name="New Certificate"
            )
            self.assertEqual(new_certificates.count(), 1)


class ResumeCertificateModelTest(TestCase):
    """Test the ResumeCertificate model delete method."""

    def setUp(self):
        """Set up test data."""
        self.candidate = Candidate.objects.create(
            email="test@example.com",
            password="testpass123",
            is_candidate=True
        )
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Test Resume",
            description="Test description",
            position="Software Developer"
        )

    def test_certificate_delete_cleans_file(self):
        """Test that deleting a certificate cleans up its file."""
        test_file = SimpleUploadedFile("test.pdf", b"test content", content_type="application/pdf")

        certificate = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Test Certificate",
            file=test_file
        )

        # Mock file operations
        with patch.object(default_storage, 'exists', return_value=True), \
                patch.object(default_storage, 'delete') as mock_delete:
            certificate.delete()

            # Verify file was deleted
            mock_delete.assert_called_once_with(certificate.file.name)

    def test_certificate_delete_handles_missing_file(self):
        """Test that deleting a certificate without file doesn't raise error."""
        certificate = ResumeCertificate.objects.create(
            resume=self.resume,
            name="Test Certificate No File"
        )

        # Should not raise an exception
        certificate.delete()

        # Verify certificate is deleted from database
        with self.assertRaises(ResumeCertificate.DoesNotExist):
            certificate.refresh_from_db()


class CertificateEmptyDataTest(TestCase):
    """Test that empty certificate arrays properly delete all certificates."""

    def setUp(self):
        self.candidate = Candidate.objects.create(
            email="empty-cert@example.com",
            password="testpass123",
            is_candidate=True
        )
        self.resume = Resume.objects.create(
            candidate=self.candidate,
            title="Test Resume",
            description="Test",
            position="Dev"
        )
        self.cert1 = ResumeCertificate.objects.create(resume=self.resume, name="Cert 1")
        self.cert2 = ResumeCertificate.objects.create(resume=self.resume, name="Cert 2")

    def test_empty_certificates_array_deletes_all_certificates(self):
        self.assertEqual(self.resume.certificates.count(), 2)
        serializer = ResumeSerializer(
            instance=self.resume,
            data={"certificates": []},
            partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_resume = serializer.save()
        self.assertEqual(updated_resume.certificates.count(), 0)

    def test_empty_certificates_data_array_deletes_all_certificates(self):
        self.assertEqual(self.resume.certificates.count(), 2)
        serializer = ResumeSerializer(
            instance=self.resume,
            data={"certificates_data": []},
            partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_resume = serializer.save()
        self.assertEqual(updated_resume.certificates.count(), 0)


class ResumeSerializerCertificateTest(TestCase):
    """Test certificate handling in ResumeSerializer."""

    def setUp(self):
        """Set up test data."""
        self.candidate = Candidate.objects.create(
            email="test@example.com",
            password="testpass123",
            is_candidate=True
        )

    def test_resume_create_with_certificates(self):
        """Test creating a resume with certificates."""
        resume_data = {

            "title": "Test Resume",
            "description": "Test description",
            "position": "Software Developer",
            "certificates_data": [
                {
                    "name": "AWS Certification",
                    "issuing_organization": "Amazon",
                    "issue_date": "2024-01-01"
                },
                {
                    "name": "Google Cloud Certification",
                    "issuing_organization": "Google",
                    "issue_date": "2024-02-01"
                }
            ]
        }

        serializer = ResumeSerializer(data=resume_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        # Pass candidate to save() like the actual view does
        resume = serializer.save(candidate=self.candidate)

        # Verify certificates were created
        self.assertEqual(resume.certificates.count(), 2)

        certificate_names = list(resume.certificates.values_list('name', flat=True))
        self.assertIn("AWS Certification", certificate_names)
        self.assertIn("Google Cloud Certification", certificate_names)

    def test_resume_update_removes_certificates(self):
        """Test that updating a resume properly removes certificates."""
        # Create resume with certificates
        resume = Resume.objects.create(
            candidate=self.candidate,
            title="Test Resume",
            description="Test description",
            position="Software Developer"
        )

        cert1 = ResumeCertificate.objects.create(
            resume=resume,
            name="Certificate 1"
        )
        cert2 = ResumeCertificate.objects.create(
            resume=resume,
            name="Certificate 2"
        )
        cert3 = ResumeCertificate.objects.create(
            resume=resume,
            name="Certificate 3"
        )

        # Update with only cert1 and cert2, removing cert3
        update_data = {
            "certificates_data": [
                {
                    "id": cert1.id,
                    "name": "Updated Certificate 1"
                },
                {
                    "id": cert2.id,
                    "name": "Updated Certificate 2"
                }
            ]
        }

        # Mock file operations
        with patch.object(default_storage, 'exists', return_value=False), \
                patch.object(default_storage, 'delete') as mock_delete:
            serializer = ResumeSerializer(instance=resume, data=update_data, partial=True)
            self.assertTrue(serializer.is_valid(), serializer.errors)

            updated_resume = serializer.save()

            # Verify only 2 certificates remain
            self.assertEqual(updated_resume.certificates.count(), 2)

            # Verify cert3 was deleted
            with self.assertRaises(ResumeCertificate.DoesNotExist):
                cert3.refresh_from_db()

            # Verify cert1 and cert2 were updated
            cert1.refresh_from_db()
            cert2.refresh_from_db()
            self.assertEqual(cert1.name, "Updated Certificate 1")
            self.assertEqual(cert2.name, "Updated Certificate 2")


class ResumeAPIIntegrationTest(APITestCase):
    """Integration tests for the full API workflow."""

    def setUp(self):
        """Set up test data."""
        self.candidate = Candidate.objects.create(
            email="test@example.com",
            password="testpass123",
            is_candidate=True
        )
        self.client.force_authenticate(user=self.candidate)

    def test_full_certificate_workflow(self):
        """Test the complete certificate workflow through the API."""
        # Create resume with certificates
        resume_data = {
            "title": "Test Resume",
            "description": "Test description",
            "position": "Software Developer",
            "certificates_data": '[{"name": "Initial Cert", "issuing_organization": "Test Org"}]'
        }

        # Would need to use the actual API endpoint for full integration test
        # This is a simplified version focusing on the serializer logic
        serializer = ResumeSerializer(data={
            **resume_data,
            "certificates_data": [{"name": "Initial Cert", "issuing_organization": "Test Org"}]
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        resume = serializer.save(candidate=self.candidate)

        # Verify initial certificate
        self.assertEqual(resume.certificates.count(), 1)
        initial_cert = resume.certificates.first()

        # Update to remove the certificate and add a new one
        update_data = {
            "certificates_data": [{"name": "New Cert", "issuing_organization": "New Org"}]
        }

        with patch.object(default_storage, 'exists', return_value=False):
            update_serializer = ResumeSerializer(
                instance=resume,
                data=update_data,
                partial=True
            )
            self.assertTrue(update_serializer.is_valid(), update_serializer.errors)
            updated_resume = update_serializer.save()

        # Verify the old certificate was deleted and new one created
        self.assertEqual(updated_resume.certificates.count(), 1)
        new_cert = updated_resume.certificates.first()
        self.assertEqual(new_cert.name, "New Cert")
        self.assertNotEqual(new_cert.id, initial_cert.id)
