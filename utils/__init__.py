import uuid as _uuid

from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .abstract_model import AbstractBaseModel
from .user_permission import IsSelfPermission
from .candidate_permission import IsCandidatePermission
from .serializers_mixins import FlexibleImageField
from .recruiter_permission import (
    IsAdminRecruiter,
    IsRecruiterPermission,
)
from .company_permission import IsCompanyApproved
from .fields.certificate import (
    validate_certificate_file,
    _inject_language_certificate_files,
    build_certificate_error_payload,
)
from .query_helpers import get_candidate_ids_by_skills
from .upload_validation import validate_uploaded_file


def encode_uid(pk):
    """Encode a UUID primary key as compact base64 (16 bytes → 22 chars)."""
    return urlsafe_base64_encode(_uuid.UUID(str(pk)).bytes)


def decode_uid(uid_b64):
    """
    Decode a base64-encoded uid back to a string pk.
    Supports both compact format (16 raw bytes) and legacy format (UUID string).
    """
    raw = urlsafe_base64_decode(uid_b64)
    if len(raw) == 16:
        return str(_uuid.UUID(bytes=raw))
    return force_str(raw)


__all__ = [
    "AbstractBaseModel",
    "IsCandidatePermission",
    "IsRecruiterPermission",
    "IsAdminRecruiter",
    "FlexibleImageField",
    "IsSelfPermission",
    "validate_certificate_file",
    "_inject_language_certificate_files",
    "build_certificate_error_payload",
    "validate_uploaded_file",
    "get_candidate_ids_by_skills",
    "encode_uid",
    "decode_uid",
]
