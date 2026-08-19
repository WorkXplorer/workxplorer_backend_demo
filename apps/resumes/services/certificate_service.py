"""
Services for handling resume certificate operations.
Provides clean architecture for certificate management including file cleanup.
"""

import logging
from typing import List, Dict, Any
from django.db import transaction
from django.utils.translation import gettext as _
from django.core.files.storage import default_storage
from ..models import ResumeCertificate, Resume
from utils.parse_date import parse_date

logger = logging.getLogger(__name__)


class CertificateService:
    """
    Service class for handling certificate operations with proper file management.
    """

    @staticmethod
    def clean_certificate_file(certificate: ResumeCertificate) -> None:
        """
        Clean up the file associated with a certificate.
        
        Args:
            certificate: ResumeCertificate instance
        """
        if certificate.file and default_storage.exists(certificate.file.name):
            try:
                default_storage.delete(certificate.file.name)
                logger.info(f"Deleted certificate file: {certificate.file.name}")
            except Exception as e:
                logger.error(f"Failed to delete certificate file {certificate.file.name}: {e}")

    @staticmethod
    def delete_certificates(certificates_queryset) -> None:
        """
        Delete certificates with proper file cleanup.
        
        Args:
            certificates_queryset: QuerySet of ResumeCertificate objects or RelatedManager
        """
        # Convert RelatedManager to QuerySet if needed
        if hasattr(certificates_queryset, 'all'):
            certificates_to_delete = list(certificates_queryset.all())
            queryset = certificates_queryset.all()
        else:
            certificates_to_delete = list(certificates_queryset)
            queryset = certificates_queryset

        # Clean up files first
        for certificate in certificates_to_delete:
            CertificateService.clean_certificate_file(certificate)

        # Then delete database records
        queryset.delete()

    @staticmethod
    def validate_certificates_data(certificates_data: List[Dict[str, Any]], resume: Resume = None) -> tuple:
        """
        Validate and process certificates data.
        
        Args:
            certificates_data: List of certificate data dictionaries
            resume: Resume instance for ownership validation (optional)
            
        Returns:
            Tuple of (validated_certificates, certificates_to_delete_ids)
            
        Raises:
            ValidationError: If validation fails
        """
        from rest_framework import serializers

        if not certificates_data:
            # If empty array provided and resume exists, mark all existing certificates for deletion
            if resume:
                existing_certificate_ids = set(resume.certificates.values_list('id', flat=True))
                return [], existing_certificate_ids
            return [], set()

        if not isinstance(certificates_data, list):
            raise serializers.ValidationError(_("Expected a list of certificate objects."))

        validated_certificates = []
        existing_certificate_ids = set()

        # Get existing certificate IDs for this resume if provided
        if resume:
            existing_certificate_ids = set(
                resume.certificates.values_list('id', flat=True)
            )

        for idx, cert_data in enumerate(certificates_data):
            if not isinstance(cert_data, dict):
                raise serializers.ValidationError(
                    f"Each certificate must be a dictionary at index {idx}."
                )

            # Handle existing certificate updates
            cert_id = cert_data.get("id")
            if cert_id:
                # Validate that the certificate belongs to this resume
                if resume and cert_id not in existing_certificate_ids:
                    raise serializers.ValidationError(
                        f"Certificate with ID {cert_id} does not belong to this resume."
                    )

                # Mark this ID as processed (for deletion detection)
                if cert_id in existing_certificate_ids:
                    existing_certificate_ids.discard(cert_id)

            # Parse dates properly
            issue_date = parse_date(cert_data.get("issue_date"))
            expiration_date = parse_date(cert_data.get("expiration_date"))

            # Validate date logic: expiration_date should not be before issue_date
            if issue_date and expiration_date and expiration_date < issue_date:
                raise serializers.ValidationError(
                    f"Expiration date cannot be before issue date for certificate at index {idx}."
                )

            validated_certificate = {
                "id": cert_id,
                "name": (cert_data.get("name", "").strip()[:200]) if cert_data.get("name") else "",
                "issuing_organization": cert_data.get("issuing_organization", "").strip()
                    if cert_data.get("issuing_organization") else "",
                "issue_date": issue_date,
                "expiration_date": expiration_date,
                "credential_id": cert_data.get("credential_id", "").strip()
                    if cert_data.get("credential_id") else "",
                "credential_url": cert_data.get("credential_url", "").strip()
                    if cert_data.get("credential_url") else "",
            }

            # Handle file field from form data
            if "file" in cert_data:
                validated_certificate["file"] = cert_data["file"]

            validated_certificates.append(validated_certificate)

        return validated_certificates, existing_certificate_ids

    @staticmethod
    @transaction.atomic
    def update_resume_certificates(resume: Resume, certificates_data: List[Dict[str, Any]]) -> None:
        """
        Update resume certificates efficiently by comparing existing vs new data.
        Only deletes certificates that are actually removed and creates new ones.
        
        Args:
            resume: Resume instance
            certificates_data: List of validated certificate data
        """
        if certificates_data is None:
            return  # No update requested

        # Validate the certificates data
        validated_certificates, certificates_to_delete_ids = CertificateService.validate_certificates_data(
            certificates_data, resume
        )

        # Fetch all existing certificates in one query for efficient lookups
        existing_certs_map = {
            cert.id: cert
            for cert in resume.certificates.all()
        }

        # Delete certificates that are no longer present
        if certificates_to_delete_ids:
            certs_to_delete = [existing_certs_map[cid] for cid in certificates_to_delete_ids if cid in existing_certs_map]
            for cert in certs_to_delete:
                CertificateService.clean_certificate_file(cert)
            resume.certificates.filter(id__in=certificates_to_delete_ids).delete()

        # Update existing certificates and create new ones
        certificates_to_create = []
        for cert_data in validated_certificates:
            cert_id = cert_data.pop("id", None)  # Remove ID from data

            if cert_id:
                # Update existing certificate using pre-fetched map
                existing_cert = existing_certs_map.get(cert_id)
                if existing_cert:
                    for field, value in cert_data.items():
                        if field != "file":  # Don't update file field for existing certificates
                            setattr(existing_cert, field, value)
                    existing_cert.save()
                else:
                    # Certificate was already deleted or doesn't exist, create new one
                    certificates_to_create.append(ResumeCertificate(resume=resume, **cert_data))
            else:
                # Create new certificate
                certificates_to_create.append(ResumeCertificate(resume=resume, **cert_data))

        # Create new certificates one by one to handle file uploads
        for cert in certificates_to_create:
            cert.save()

    @staticmethod
    def create_resume_certificates(resume: Resume, certificates_data: List[Dict[str, Any]]) -> None:
        """
        Create new resume certificates in bulk.
        
        Args:
            resume: Resume instance
            certificates_data: List of validated certificate data
        """
        if not certificates_data:
            return

        # Create certificates one by one to handle file uploads properly
        for cert_data in certificates_data:
            # Remove ID if present (not needed for creation)
            cert_data.pop("id", None)
            certificate = ResumeCertificate(resume=resume, **cert_data)
            certificate.save()
