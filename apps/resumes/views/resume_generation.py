"""
API views for AI-powered resume generation.
"""

import base64
import logging
from datetime import date
from typing import Optional

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.throttling import UserRateThrottle
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes
import django_rq
from django.utils.translation import gettext as _

from core.responses import APIResponse
from utils.candidate_permission import IsCandidatePermission
from ..serializers import (
    ResumeGenerationRequestSerializer,
    ResumeGenerationJobStatusSerializer,
)
from ..tasks import process_resume_generation
from apps.subscriptions.services import SubscriptionService
from apps.general.services.job_queue_service import JobQueueService

logger = logging.getLogger(__name__)


class GenerateResumeView(APIView):
    """
    API endpoint for AI-powered resume generation.
    
    This endpoint accepts either a text prompt, a resume file (PDF/DOCX), or both,
    and uses the AI provider to generate a structured resume.
    
    The processing is done asynchronously via RQ (Redis Queue) to handle
    the AI API call efficiently.
    
    ## Authentication
    Requires candidate authentication.
    
    ## Request Format
    **Content-Type:** `multipart/form-data`
    
    ### Fields:
    - `prompt` (optional): Free-form text description or instructions
    - `file` (optional): Resume file in PDF or DOCX format (max 10MB)
    
    **Note:** At least one of `prompt` or `file` must be provided.
    
    ## Processing Logic
    - **Prompt only**: Generates resume based on the text description
    - **File only**: Parses and analyzes the file content to create resume
    - **Both**: Performs combined analysis using file context and prompt instructions
    
    ## Response
    Returns a job ID that can be used to check the processing status.
    """
    
    permission_classes = [IsAuthenticated, IsCandidatePermission]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UserRateThrottle]
    throttle_scope = 'resume_generation'
    
    @extend_schema(
        summary="Generate resume using AI",
        description="""
        Generate a structured resume using the AI provider.
        
        Accepts either a text prompt, a resume file (PDF/DOCX), or both.
        Processing is done asynchronously - returns a job ID to track status.
        
        ## Skill Mapping
        The system uses semantic matching to map described skills to database skills:
        - "good communicator" → "Communication"
        - "people person" → "Interpersonal Skills"
        - "team player" → "Teamwork"
        
        ## Domain Matching
        Automatically identifies and matches professional domains from database.
        
        ## Language Support
        Detects input language (English, Russian, Uzbek) and generates
        appropriate output.
        """,
        request={
            "multipart/form-data": ResumeGenerationRequestSerializer,
        },
        responses={
            202: OpenApiResponse(
                response=dict,
                description="Job queued successfully",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "message": "Resume generation job queued successfully",
                            "data": {
                                "job_id": "abc123def456",
                                "status": "queued",
                                "check_status_url": "/api/v1/resumes/generate-status/abc123def456/",
                            },
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(
                response=dict,
                description="Validation error",
                examples=[
                    OpenApiExample(
                        "Missing Input",
                        value={
                            "success": False,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": "Validation failed",
                                "field_errors": {
                                    "non_field_errors": ["At least one of 'prompt' or 'file' must be provided."]
                                },
                            },
                        },
                    ),
                ],
            ),
            401: OpenApiResponse(description="Authentication required"),
            403: OpenApiResponse(description="Permission denied - candidates only"),
        },
        tags=["Resume Generation"],
    )
    def post(self, request, *args, **kwargs):
        """
        Queue a resume generation job.
        
        Returns a job ID that can be used to check processing status.
        """
        # Validate request
        serializer = ResumeGenerationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return APIResponse.validation_error(
                message=_("Validation failed"),
                field_errors=serializer.errors,
            )
        
        validated_data = serializer.validated_data
        prompt = validated_data.get('prompt', '').strip()
        file_obj = validated_data.get('file')
        
        # Determine source type and prepare content
        source_type: str
        content: str
        file_extension: Optional[str] = None
        
        if file_obj and prompt:
            # Combined mode
            source_type = 'combined'
            # Read file content
            file_content = file_obj.read()
            content = base64.b64encode(file_content).decode('utf-8')
            # Get file extension
            file_extension = f".{file_obj.name.split('.')[-1].lower()}"
        elif file_obj:
            # File only mode
            source_type = 'file'
            file_content = file_obj.read()
            content = base64.b64encode(file_content).decode('utf-8')
            file_extension = f".{file_obj.name.split('.')[-1].lower()}"
        else:
            # Prompt only mode
            source_type = 'prompt'
            content = prompt
        
        # Get candidate ID
        candidate_id = str(request.user.candidate.id) if hasattr(request.user, 'candidate') else str(request.user.id)
        
        # Check subscription-based AI generation limit
        candidate = request.user.candidate if hasattr(request.user, 'candidate') else request.user
        limit_check = SubscriptionService.check_ai_generation_limit(candidate)
        if not limit_check["allowed"]:
            return APIResponse.forbidden(
                message=limit_check["error"],
                details={
                    "max_generations_per_month": limit_check["max_generations_per_month"],
                    "current_usage": limit_check["current_usage"],
                    "plan_name": limit_check["plan_name"],
                },
            )
        
        # Increment usage ATOMICALLY before enqueue to prevent race condition
        # (TOCTOU: view checks limit → async task increments; concurrent requests bypass)
        from apps.subscriptions.models import CandidateFeatureUsage, SubscriptionFeature
        from apps.subscriptions.services import FEATURE_AI_RESUME_GENERATION
        try:
            feature = SubscriptionFeature.objects.get(
                code=FEATURE_AI_RESUME_GENERATION, is_active=True,
            )
            CandidateFeatureUsage.increment_usage(candidate, feature)
        except Exception as e:
            logger.error(f"Failed to increment usage for candidate {candidate_id}: {e}")
        
        # Register job queue entry for retry tracking
        job_queue = JobQueueService.register_job(
            job_type="resume_generation",
            target_date=date.today(),
            target_id=candidate_id,
            target_name=candidate.email if hasattr(candidate, 'email') else None,
        )
        # Override max_retries for resume generation
        job_queue.max_retries = 3
        job_queue.save(update_fields=["max_retries"])
        
        # Enqueue the task
        try:
            queue = django_rq.get_queue('default')
            job = queue.enqueue(
                process_resume_generation,
                candidate_id=candidate_id,
                source_type=source_type,
                content=content,
                file_extension=file_extension,
                additional_instructions=prompt if source_type in ('file', 'combined') else "",
                job_timeout=300,  # 5 minute timeout
                job_queue_id=str(job_queue.id),
            )
            
            logger.info(
                f"Resume generation job queued: {job.id} for candidate {candidate_id}"
            )
            
            return APIResponse.success(
                data={
                    "job_id": job.id,
                    "status": "queued",
                    "check_status_url": f"/api/v1/resumes/generate-status/{job.id}/",
                },
                message=_("Resume generation job queued successfully"),
                status_code=202,  # Accepted
            )
            
        except Exception as e:
            logger.error(f"Failed to queue resume generation job: {e}")
            return APIResponse.server_error(
                message=_("Failed to queue resume generation job"),
                details=str(e),
            )


class ResumeGenerationStatusView(APIView):
    """
    API endpoint to check the status of a resume generation job.
    
    ## Authentication
    Requires candidate authentication.
    
    ## Response Statuses
    - `queued`: Job is waiting to be processed
    - `started`: Job is currently being processed
    - `finished`: Job completed successfully (result available)
    - `failed`: Job failed (error message available)
    """
    
    permission_classes = [IsAuthenticated, IsCandidatePermission]
    
    @extend_schema(
        summary="Check resume generation job status",
        description="""
        Check the status of an asynchronous resume generation job.
        
        ## Statuses
        - `queued`: Waiting to start
        - `started`: Currently processing
        - `finished`: Complete with result
        - `failed`: Failed with error message
        """,
        parameters=[
            OpenApiParameter(
                name="job_id",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="Job ID returned by the generate endpoint",
                required=True,
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ResumeGenerationJobStatusSerializer,
                description="Job status retrieved",
            ),
            404: OpenApiResponse(description="Job not found"),
        },
        tags=["Resume Generation"],
    )
    def get(self, request, job_id: str, *args, **kwargs):
        """
        Get the status of a resume generation job.
        """
        try:
            queue = django_rq.get_queue('default')
            job = queue.fetch_job(job_id)
            
            if not job:
                return APIResponse.not_found(
                    message=_("Job not found"),
                    resource=_("Resume generation job"),
                )
            
            # Build response based on job status
            response_data = {
                "job_id": job_id,
                "status": job.get_status(),
                "created_at": job.created_at.isoformat() if job.created_at else None,
            }
            
            if job.is_finished:
                result = job.result
                if result and result.get('success'):
                    response_data["result"] = result.get('data')
                    response_data["error"] = None
                else:
                    # Task returned but reported failure internally — treat as failed
                    response_data["status"] = "failed"
                    response_data["result"] = None
                    response_data["error"] = result.get('error') if result else _("Unknown error")
            elif job.is_failed:
                response_data["result"] = None
                response_data["error"] = _extract_error_message(job)
            else:
                response_data["result"] = None
                response_data["error"] = None
            
            return APIResponse.success(data=response_data)
            
        except Exception as e:
            logger.error(f"Error fetching job status for {job_id}: {e}")
            return APIResponse.server_error(
                message=_("Failed to retrieve job status"),
                details=str(e),
            )


class ResumeGenerationUsageView(APIView):
    """
    API endpoint to get the current AI resume generation usage for the authenticated candidate.
    Returns current monthly usage vs. plan limit so the frontend can display a counter.
    """

    permission_classes = [IsAuthenticated, IsCandidatePermission]

    @extend_schema(
        summary="Get AI resume generation usage",
        description="Returns the current month's AI resume generation usage and plan limit for the candidate.",
        responses={
            200: OpenApiResponse(
                response=dict,
                description="Usage information",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "data": {
                                "current_usage": 1,
                                "max_generations_per_month": 3,
                                "plan_name": "Free",
                                "allowed": True,
                            },
                        },
                    )
                ],
            ),
        },
        tags=["Resume Generation"],
    )
    def get(self, request, *args, **kwargs):
        candidate = request.user.candidate if hasattr(request.user, 'candidate') else request.user
        result = SubscriptionService.check_ai_generation_limit(candidate)
        return APIResponse.success(data={
            "current_usage": result["current_usage"],
            "max_generations_per_month": result["max_generations_per_month"],
            "plan_name": result["plan_name"],
            "allowed": result["allowed"],
        })


def _extract_error_message(job) -> str:
    # ponytail: generic message, no traceback content exposed to user
    return _("Job failed")


# Create view instances
generate_resume_view = GenerateResumeView.as_view()
resume_generation_status_view = ResumeGenerationStatusView.as_view()
resume_generation_usage_view = ResumeGenerationUsageView.as_view()
