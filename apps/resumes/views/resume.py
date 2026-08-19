import logging
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django_rq import enqueue
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiExample, inline_serializer

from ..serializers import ResumeSerializer, WorkStatusSerializer
from ..models import Resume, ResumeCertificate
from django.http import Http404
from rest_framework.permissions import AllowAny, IsAuthenticated
from apps.authentication.models import Candidate
from apps.matching.services.embedding_tasks import generate_resume_embedding_task
from rest_framework.views import APIView
from ..models.choices import WorkStatus
from apps.authentication.transitions import update_candidate_step, CREATE_RESUME

from utils import (
    validate_certificate_file,
    _inject_language_certificate_files,
    build_certificate_error_payload,
)
from utils.virus_scanner import VirusScanError
from utils.language import get_request_language

from core.responses import APIResponse
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


@extend_schema_view(
    get=extend_schema(
        summary="Retrieve resume",
        description="Get a single resume by ID with all related data including skills, experiences, certificates, "
                    "language certificates, and candidate profile info. "
                    "Candidates can only retrieve their own resumes. Recruiters can view any resume.",
        responses={
            200: OpenApiResponse(
                response=ResumeSerializer,
                description="Resume data with all nested relations",
            ),
            403: OpenApiResponse(description="Not authenticated"),
            404: OpenApiResponse(description="Resume not found or not accessible"),
        },
    ),
)
class RetrieveResumeView(generics.RetrieveAPIView):
    """
    Get resume by its id with all related data.
    
    Permissions:
    - Authenticated users only
    - Candidates can only view their own resumes
    - Recruiters can view any resume
    """

    def get_queryset(self):
        return Resume.objects.select_related(
            "candidate",
            "candidate__candidateprofile",
            "candidate__candidateprofile__citizenship",
            "candidate__edupartner",
            "domain"
        ).prefetch_related(
            "resume_skills__skill__category",
            "experiences",
            "certificates",
            "language_certificates__language"
        )

    serializer_class = ResumeSerializer
    permission_classes = [IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        from apps.vacancies.services.demo_data import get_demo_resume

        demo_resume = get_demo_resume(self.kwargs["id"])
        if demo_resume is not None:
            return Response(demo_resume)

        return super().retrieve(request, *args, **kwargs)

    def get_object(self):
        resume_id = self.kwargs["id"]
        try:
            resume = self.get_queryset().get(id=resume_id)

            # Permission check: Candidates can only view their own resumes
            user = self.request.user
            if user.is_candidate:
                # Check if this resume belongs to the logged-in candidate
                if resume.candidate.id != user.id:
                    raise Http404("Resume not found")

            return resume
        except Resume.DoesNotExist:
            raise Http404("Resume not found")


@extend_schema_view(
    post=extend_schema(
        summary="Create resume",
        description="Create a new resume for the authenticated candidate. "
                    "Supports JSON and multipart/form-data. "
                    "Certificate files can be uploaded via the 'certificates' field. "
                    "Embedding generation is enqueued asynchronously.",
        request=inline_serializer(
            "CreateResumeRequest",
            fields={
                "title": serializers.CharField(required=False, help_text="Resume title (max 140 chars)"),
                "description": serializers.CharField(required=False, help_text="Resume description"),
                "position": serializers.CharField(required=False, help_text="Desired position"),
                "domain": serializers.IntegerField(required=False, help_text="Domain/professional field ID"),
                "work_status": serializers.CharField(required=False, help_text="Work status (e.g. ACTIVELY_LOOKING)"),
                "current_salary": serializers.DecimalField(max_digits=15, decimal_places=2, required=False),
                "salary_currency": serializers.CharField(required=False),
                "salary_hide": serializers.BooleanField(required=False),
                "skills_data": serializers.JSONField(
                    required=False,
                    help_text='[{"skill_id": <int>, "minimum_years": <int>, "proficiency_level": "BEGINNER|INTERMEDIATE|ADVANCED|EXPERT"}]',
                ),
                "experiences_data": serializers.JSONField(
                    required=False,
                    help_text='[{"company": "...", "role": "...", "country": "...", "city": "...", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "description": "..."}]',
                ),
                "certificates_data": serializers.JSONField(
                    required=False,
                    help_text='[{"name": "...", "issuing_organization": "...", "issue_date": "YYYY-MM-DD", "expiration_date": "YYYY-MM-DD", "credential_id": "...", "credential_url": "..."}]',
                ),
                "language_certificates_data": serializers.JSONField(
                    required=False,
                    help_text='[{"language_id": <int>, "level": "A1|A2|B1|B2|C1|C2", "file": <upload>}]',
                ),
                "certificates": serializers.ListField(
                    child=serializers.FileField(),
                    required=False,
                    help_text="Certificate file uploads (jpg, jpeg, png, svg, zip, max 3MB each)",
                ),
            },
        ),
        responses={
            201: OpenApiResponse(
                response=ResumeSerializer,
                description="Resume created successfully",
            ),
            400: OpenApiResponse(description="Validation error or certificate file error"),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
)
class CreateResumeView(generics.CreateAPIView):
    """
    Create a new resume with optional certificate file uploads.

    Automatically sets the candidate from the authenticated user.
    Enqueues embedding generation in background via Redis queue.

    Accepts:
        - JSON data for resume fields
        - multipart/form-data with 'certificates' key for file uploads

    Certificate files:
        - Allowed formats: jpg, jpeg, png, svg, zip
        - Max file size: 3MB per file
        - Each file creates a separate ResumeCertificate object
    """

    queryset = Resume.objects.all()
    serializer_class = ResumeSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_candidate(self):
        """Robust candidate lookup: user may be Candidate instance or multi-table subclass."""
        user = getattr(self.request, "user", None)
        if not user or user.is_anonymous:
            return None
        # If request.user is already a Candidate instance
        if isinstance(user, Candidate):
            return user
        # Try direct PK lookup (works when Candidate uses same PK as user)
        cand = Candidate.objects.filter(pk=user.pk).first()
        if cand:
            return cand
        # Fallback for multi-table inheritance pointer field name
        for ptr_field in ("customuser_ptr_id", "id", "customuser_ptr"):
            if hasattr(Candidate, ptr_field) or ptr_field.endswith("_id"):
                cand = Candidate.objects.filter(**{f"{ptr_field}": user.pk}).first()
                if cand:
                    return cand
        return None

    def validate_certificate_files(self, files):
        """Return a list of VirusScanError exceptions collected per file."""
        errors = []
        for f in files:
            try:
                validate_certificate_file(f)
            except VirusScanError as exc:
                errors.append(exc)
        return errors

    def create(self, request, *args, **kwargs):
        candidate = self.get_candidate()
        if not candidate:
            return APIResponse.bad_request(
                message=_("Candidate profile not found")
            )

        # support both 'certificates' and 'certificates[]' keys
        certificate_files = (
                request.FILES.getlist("certificates")
                or request.FILES.getlist("certificates[]")
                or []
        )

        if certificate_files:
            validation_errors = self.validate_certificate_files(certificate_files)
            if validation_errors:
                error_payload = build_certificate_error_payload(
                    validation_errors, get_request_language()
                )
                return APIResponse.error(
                    message=error_payload["message"],
                    code=error_payload["code"],
                    details=error_payload["details"],
                    field_errors=error_payload["field_errors"],
                )

        # Inject language certificate files into language_certificates_data
        data = request.data.copy()
        data = _inject_language_certificate_files(request, data)

        with transaction.atomic():
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            # pass candidate to serializer.save() so Resume candidate is set
            resume = serializer.save(candidate=candidate)

            # save uploaded certificate files
            for f in certificate_files:
                cert_name = f.name[:200] if f.name else ""
                ResumeCertificate.objects.create(resume=resume, file=f, name=cert_name)
            update_candidate_step(candidate, CREATE_RESUME)
        # enqueue embedding generation (non-blocking)
        try:
            enqueue(generate_resume_embedding_task, resume.id)
        except Exception:
            logger.exception("Failed to enqueue resume embedding task")

        return APIResponse.created(
            data=serializer.data,
            message=_("Resume created successfully"),
        )


@extend_schema_view(
    put=extend_schema(
        summary="Update resume",
        description="Update an existing resume. Only the owner candidate can update. "
                    "Supports JSON and multipart/form-data for certificate file uploads. "
                    "Embedding is regenerated asynchronously on update.",
        request=inline_serializer(
            "UpdateResumeRequest",
            fields={
                "title": serializers.CharField(required=False),
                "description": serializers.CharField(required=False),
                "position": serializers.CharField(required=False),
                "domain": serializers.IntegerField(required=False),
                "work_status": serializers.CharField(required=False),
                "current_salary": serializers.DecimalField(max_digits=15, decimal_places=2, required=False),
                "salary_currency": serializers.CharField(required=False),
                "salary_hide": serializers.BooleanField(required=False),
                "skills_data": serializers.JSONField(required=False),
                "experiences_data": serializers.JSONField(required=False),
                "certificates_data": serializers.JSONField(required=False),
                "language_certificates_data": serializers.JSONField(required=False),
                "certificates": serializers.ListField(child=serializers.FileField(), required=False),
            },
        ),
        responses={
            200: OpenApiResponse(description="Resume updated successfully", response=ResumeSerializer),
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Resume not found"),
        },
    ),
    patch=extend_schema(
        summary="Partially update resume",
        description="Partially update an existing resume. Supports same fields as PUT.",
        request=inline_serializer(
            "PatchResumeRequest",
            fields={
                "title": serializers.CharField(required=False),
                "description": serializers.CharField(required=False),
                "position": serializers.CharField(required=False),
                "domain": serializers.IntegerField(required=False),
                "work_status": serializers.CharField(required=False),
                "current_salary": serializers.DecimalField(max_digits=15, decimal_places=2, required=False),
                "salary_currency": serializers.CharField(required=False),
                "salary_hide": serializers.BooleanField(required=False),
                "skills_data": serializers.JSONField(required=False),
                "experiences_data": serializers.JSONField(required=False),
                "certificates_data": serializers.JSONField(required=False),
                "language_certificates_data": serializers.JSONField(required=False),
            },
        ),
        responses={
            200: OpenApiResponse(description="Resume updated successfully", response=ResumeSerializer),
            400: OpenApiResponse(description="Validation error"),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Resume not found"),
        },
    ),
)
class UpdateResumeView(generics.UpdateAPIView):
    """
    Update an existing resume.
    Only the owner (candidate) can update their resume.
    """

    serializer_class = ResumeSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def validate_certificate_files(self, files):
        """Return a list of VirusScanError exceptions collected per file."""
        errors = []
        for f in files:
            try:
                validate_certificate_file(f)
            except VirusScanError as exc:
                errors.append(exc)
        return errors

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if not user or user.is_anonymous:
            return Resume.objects.none()
        # Candidate may be multi-table subclass -> filter by candidate PK
        return Resume.objects.filter(candidate_id=user.pk)

    def get_object(self):
        queryset = self.get_queryset()
        lookup = (
                self.kwargs.get("pk")
                or self.kwargs.get("id")
                or self.kwargs.get("resume_id")
        )
        try:
            return queryset.get(pk=lookup)
        except Resume.DoesNotExist:
            raise Http404("Resume not found")

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # Handle certificate files from form data
        # Support both 'certificates' and 'certificates[]' keys
        certificate_files = (
            request.FILES.getlist("certificates")
            or request.FILES.getlist("certificates[]")
            or []
        )
        if certificate_files:
            validation_errors = self.validate_certificate_files(certificate_files)
            if validation_errors:
                error_payload = build_certificate_error_payload(
                    validation_errors, get_request_language()
                )
                return APIResponse.error(
                    message=error_payload["message"],
                    code=error_payload["code"],
                    details=error_payload["details"],
                    field_errors=error_payload["field_errors"],
                )

        partial = kwargs.pop("partial", False)

        # Prepare data for serializer, handling both JSON and form data
        data = request.data.copy()

        # IMPORTANT: request.data merges FILES into data, which overwrites text
        # fields with file objects when the same field name is used for both.
        # Use request.POST for text-only access to avoid this issue.
        certificates_field = request.POST.get('certificates')
        if certificates_field is None:
            certificates_field = request.POST.get('certificates_data')
        if certificates_field is None:
            # For JSON requests (POST is empty), fall back to parsed data
            certificates_field = data.get('certificates_data')

        # Process certificates if the field is present (including empty array/string)
        if certificates_field is not None or certificate_files:
            import json

            certificates_to_keep_ids = []

            # Parse the certificates field from form data
            if certificates_field is not None:
                try:
                    # Handle JSON string from form data
                    if isinstance(certificates_field, str):
                        if certificates_field.strip() == '' or certificates_field.strip() == '[]':
                            # Empty string or empty array = delete all
                            certificates_to_keep_ids = []
                        else:
                            parsed_certs = json.loads(certificates_field)
                            if isinstance(parsed_certs, list):
                                certificates_to_keep_ids = [
                                    cert.get('id') for cert in parsed_certs
                                    if isinstance(cert, dict) and cert.get('id')
                                ]
                    elif isinstance(certificates_field, list):
                        # Already parsed list
                        certificates_to_keep_ids = [
                            cert.get('id') for cert in certificates_field
                            if isinstance(cert, dict) and cert.get('id')
                        ]
                except (json.JSONDecodeError, TypeError, AttributeError):
                    # If parsing fails and files are uploaded, keep all existing certificates
                    if certificate_files:
                        certificates_to_keep_ids = list(instance.certificates.values_list('id', flat=True))
                    else:
                        certificates_to_keep_ids = []
            else:
                # If certificates_field is not provided but files are uploaded,
                # keep all existing certificates (append mode)
                if certificate_files:
                    certificates_to_keep_ids = list(instance.certificates.values_list('id', flat=True))

            # Build certificates data array for the serializer
            certificates_data = []

            # Add existing certificates that should be kept
            for cert in instance.certificates.filter(id__in=certificates_to_keep_ids):
                certificates_data.append({
                    'id': cert.id,
                    'name': cert.name,
                    'issuing_organization': cert.issuing_organization or '',
                    'issue_date': cert.issue_date.isoformat() if cert.issue_date else None,
                    'expiration_date': cert.expiration_date.isoformat() if cert.expiration_date else None,
                    'credential_id': cert.credential_id or '',
                    'credential_url': cert.credential_url or '',
                })

            # Add new certificate files
            for f in certificate_files:
                certificates_data.append({
                    'file': f,
                    'name': f.name[:200] if f.name else '',
                    'issuing_organization': '',
                    'issue_date': None,
                    'expiration_date': None,
                    'credential_id': '',
                    'credential_url': '',
                })

            # Set certificates_data for the serializer to handle
            data['certificates_data'] = certificates_data

        # Inject language certificate files into language_certificates_data
        data = _inject_language_certificate_files(request, data)

        with transaction.atomic():
            serializer = self.get_serializer(
                instance, data=data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            resume = serializer.save()

        try:
            enqueue(generate_resume_embedding_task, resume.id)
        except Exception:
            logger.exception("Failed to enqueue resume embedding task")

        return APIResponse.success(
            data=serializer.data,
            message=_("Resume updated successfully"),
        )


@extend_schema_view(
    delete=extend_schema(
        summary="Delete resume (soft)",
        description="Soft-delete a resume by setting is_active=False. "
                    "Only the owner candidate can delete their resume.",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "DeleteResumeResponse",
                    fields={
                        "resume_id": serializers.UUIDField(),
                        "title": serializers.CharField(),
                    },
                ),
                description="Resume deleted successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {"resume_id": "550e8400-e29b-41d4-a716-446655440000", "title": "Software Engineer Resume"},
                            "message": "Resume deleted successfully",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                ],
            ),
            401: OpenApiResponse(description="Authentication required"),
            404: OpenApiResponse(description="Resume not found or not accessible"),
        },
    ),
)
class DeleteResumeView(generics.DestroyAPIView):
    """
    Delete a resume (soft delete by setting is_active=False).
    Only the owner (candidate) can delete their resume.
    
    DELETE /api/resumes/<uuid:id>/delete/
    
    Permission checks:
    - User must be authenticated
    - User must be a candidate
    - Resume must belong to the candidate
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Query optimization: Filter at database level.
        Only return resumes owned by the current candidate.
        """
        user = getattr(self.request, "user", None)
        if not user or user.is_anonymous:
            return Resume.objects.none()

        # Only candidates can delete resumes
        if not user.is_candidate:
            return Resume.objects.none()

        # Filter resumes to only those owned by the current candidate
        # This ensures permission check at query level
        return Resume.objects.filter(candidate_id=user.id, is_active=True)

    def get_object(self):
        """
        Get the resume to delete with permission checks.
        Raises Http404 if resume doesn't exist or doesn't belong to candidate.
        """
        queryset = self.get_queryset()
        lookup = self.kwargs.get("id") or self.kwargs.get("pk")

        try:
            return queryset.get(pk=lookup)
        except Resume.DoesNotExist:
            raise Http404("Resume not found or you don't have permission to delete it")

    def destroy(self, request, *args, **kwargs):
        """
        Soft delete: set is_active=False instead of actually deleting.
        Preserves data for audit purposes and potential recovery.
        """
        instance = self.get_object()

        # Soft delete implementation
        instance.is_active = False
        instance.save(update_fields=['is_active'])

        return APIResponse.success(
            data={
                "resume_id": str(instance.id),
                "title": instance.title,
            },
            message=_("Resume deleted successfully"),
        )


@extend_schema_view(
    get=extend_schema(
        summary="List my resumes",
        description="List all active resumes for the authenticated candidate. "
                    "Includes skills, experiences, certificates, and candidate profile info.",
        responses={
            200: OpenApiResponse(
                response=ResumeSerializer(many=True),
                description="List of candidate's resumes",
            ),
            401: OpenApiResponse(description="Authentication required"),
        },
    ),
)
class CandidateResumeListView(generics.ListAPIView):
    """
    List resumes created by the current candidate, including work experiences.
    Optimized to avoid duplicate queries and unnecessary joins.
    """

    serializer_class = ResumeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filter resumes to only those created by the current candidate.
        Uses user.id directly to avoid duplicate Candidate queries.
        """
        user = self.request.user

        if not user.is_candidate:
            return Resume.objects.none()

        return (
            Resume.objects.filter(candidate_id=user.id, is_active=True)
            .select_related(
                "domain",
                "candidate__edupartner",
                "candidate__candidateprofile",
                "candidate__candidateprofile__citizenship"
            )
            .prefetch_related(
                "resume_skills__skill__category", "experiences", "certificates",
                "language_certificates__language"
            )
            .order_by("-created_at")
        )


class WorkStatusListView(APIView):
    """
    API to list only job seeking work status choices.
    
    Supports localization via Accept-Language header:
    - en: English (default)
    - ru: Russian
    - uz: Uzbek
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="List work statuses",
        description="Get the list of job-seeking work status choices. "
                    "Supports localization via Accept-Language header (en, ru, uz).",
        responses={
            200: OpenApiResponse(
                response=WorkStatusSerializer(many=True),
                description="List of work status choices with labels",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": [
                                {"value": "ACTIVELY_LOOKING", "label": "Actively looking"},
                                {"value": "OPEN_TO_OFFERS", "label": "Open to offers"},
                                {"value": "NOT_LOOKING", "label": "Not looking"},
                            ],
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                ],
            ),
        },
    )
    def get(self, request, *args, **kwargs):
        """
        Return the list of job seeking work statuses in the requested language.
        """
        language = get_request_language()
        statuses = WorkStatus.get_localized_statuses(language)
        
        # Transform to match expected format with 'value' key
        work_status_choices = [
            {"value": status["key"], "label": status["label"]}
            for status in statuses
        ]
        
        serializer = WorkStatusSerializer(work_status_choices, many=True)
        return Response(serializer.data)


class SetMainResumeView(APIView):
    """
    Set a resume as the candidate's main/primary resume.

    POST /api/resumes/<uuid:id>/set-main/

    Automatically unsets any other main resume for this candidate.
    Only the resume owner can set it as main.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Set main resume",
        description="Set a resume as the candidate's primary (main) resume. "
                    "Automatically unsets any other main resume for this candidate.",
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    "SetMainResumeResponse",
                    fields={
                        "resume_id": serializers.UUIDField(),
                        "title": serializers.CharField(),
                    },
                ),
                description="Resume set as main successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {"resume_id": "550e8400-e29b-41d4-a716-446655440000", "title": "Software Engineer Resume"},
                            "message": "Resume set as main",
                            "timestamp": "2026-06-30T10:00:00+00:00",
                        },
                        status_codes=["200"],
                    ),
                ],
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="User is not a candidate"),
            404: OpenApiResponse(description="Resume not found"),
        },
    )
    def post(self, request, id):
        user = request.user

        # Check user is a candidate
        if not user.is_candidate:
            return APIResponse.forbidden(
                message=_("Only candidates can set main resumes")
            )

        # Find the resume
        try:
            resume = Resume.objects.get(id=id, candidate_id=user.id)
        except Resume.DoesNotExist:
            return APIResponse.not_found(
                message=_("Resume not found or you don't have permission")
            )

        # Set as main (the model's save() method handles unsetting others)
        resume.is_main = True
        resume.save()

        return APIResponse.success(
            data={
                "resume_id": str(resume.id),
                "title": resume.title,
            },
            message=_("Resume set as main"),
        )


# Export view instances
retrieve_resume_view = RetrieveResumeView.as_view()
create_resume_view = CreateResumeView.as_view()
update_resume_view = UpdateResumeView.as_view()
delete_resume_view = DeleteResumeView.as_view()
candidate_resume_list_view = CandidateResumeListView.as_view()
work_status_list_view = WorkStatusListView.as_view()
set_main_resume_view = SetMainResumeView.as_view()
