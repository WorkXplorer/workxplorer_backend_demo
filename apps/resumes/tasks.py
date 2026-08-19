"""
RQ Tasks for resume generation.

These tasks handle asynchronous processing of AI-powered resume generation,
including automatic saving of generated resumes, job queue status updates,
and subscription usage tracking.
"""

import logging
import uuid
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext as _

import django_rq
from utils.prompt_sanitizer import detect_prompt_injection

from .services.resume_generation import (
    generate_resume,
    map_ai_response_to_database,
    extract_file_text,
)
from .services.github_service import (
    fetch_github_data,
    format_github_context_for_prompt,
)

logger = logging.getLogger(__name__)


class ResumeGenerationTaskError(Exception):
    """Custom exception for resume generation task errors."""
    pass


def process_resume_generation(
    candidate_id: str,
    source_type: str,
    content: str,
    file_extension: Optional[str] = None,
    additional_instructions: str = "",
    job_queue_id: Optional[str] = None,
    retry_attempt: int = 0,
) -> dict:
    """
    RQ task to process resume generation asynchronously.

    This task:
    1. Extracts text from file if provided
    2. Calls the AI provider for resume generation
    3. Maps AI response to database entities (skills, domains, languages)
    4. Auto-saves the generated resume to the database
    5. Updates JobQueue status for retry tracking
    6. Increments CandidateFeatureUsage for subscription limits

    Args:
        candidate_id: UUID of the candidate requesting generation
        source_type: Type of source ('prompt', 'file', 'combined')
        content: Either the prompt text or binary file content (as base64)
        file_extension: File extension if content is a file (e.g., '.pdf')
        additional_instructions: Additional instructions for AI
        job_queue_id: UUID of JobQueue entry for retry tracking
        retry_attempt: Current retry attempt number

    Returns:
        Dict containing:
            - success: bool
            - data: Generated and saved resume data
            - error: Error message if failed

    Raises:
        ResumeGenerationTaskError: If processing fails
    """
    import base64

    from apps.general.services.job_queue_service import JobQueueService

    task_id = str(uuid.uuid4())[:8]
    logger.info(f"[Task {task_id}] Starting resume generation for candidate {candidate_id}")

    original_source_text = ""
    try:
        # Process file content if needed
        processed_content = content
        original_source_text = content
        if source_type in ('file', 'combined') and file_extension:
            logger.info(f"[Task {task_id}] Extracting text from {file_extension} file")
            try:
                file_bytes = base64.b64decode(content)
                processed_content = extract_file_text(file_bytes, file_extension)

                if not processed_content.strip():
                    raise ResumeGenerationTaskError(
                        "No extractable text found in the uploaded file."
                    )

                logger.info(f"[Task {task_id}] Extracted {len(processed_content)} characters from file")

                # Save original source text BEFORE appending additional_instructions
                # to prevent prompt injection from poisoning hallucination validation
                original_source_text = processed_content

                if source_type == 'combined' and additional_instructions:
                    processed_content = f"""
Extracted resume content:
{processed_content}

Additional instructions:
{additional_instructions}
"""
            except Exception as e:
                logger.error(f"[Task {task_id}] File extraction error: {e}")
                raise ResumeGenerationTaskError(f"Failed to extract file content: {str(e)}")

        # Call the AI provider for resume generation
        logger.info(f"[Task {task_id}] Calling AI provider for resume generation")
        try:
            # Load candidate profile to fetch additional context
            from apps.profiles.models import CandidateProfile
            has_github_context = False
            has_social_url = False
            profile_context = ""

            try:
                profile = CandidateProfile.objects.filter(
                    candidate_id=candidate_id
                ).first()

                if profile:
                    if profile.github_url:
                        logger.info(f"[Task {task_id}] Fetching GitHub data for candidate")
                        github_data = fetch_github_data(profile.github_url)
                        if github_data.get("success"):
                            github_context = format_github_context_for_prompt(github_data)
                            if github_context:
                                profile_context += (
                                    "\n\n## GitHub Context (from candidate's actual GitHub profile - use this data professionally):\n"
                                    + github_context
                                )
                                has_github_context = True
                                logger.info(
                                    f"[Task {task_id}] GitHub data fetched: "
                                    f"{github_data['data']['public_repos']} repos"
                                )
                        else:
                            logger.warning(
                                f"[Task {task_id}] GitHub fetch failed: {github_data.get('error')}"
                            )

                    if profile.social_url:
                        profile_context += (
                            f"\n\n## Portfolio Link (for informational purposes):\n{profile.social_url}"
                        )
                        has_social_url = True

                    if profile.linkedin_url:
                        profile_context += (
                            f"\n\n## LinkedIn URL (for reference):\n{profile.linkedin_url}"
                        )
            except Exception as e:
                logger.warning(f"[Task {task_id}] Could not load candidate profile: {e}")

            # Save original source text for hallucination validation.
            # For prompt-only mode, original_source_text is set here (no file).
            # For file/combined mode, it was already set after text extraction above.
            if source_type == 'prompt':
                original_source_text = processed_content

            if profile_context:
                # Sanity-check external profile data for injection attempts
                injection_match = detect_prompt_injection(profile_context)
                if injection_match:
                    logger.warning(
                        "Prompt injection pattern in profile data: '%s' — stripping profile context",
                        injection_match,
                    )
                    profile_context = ""
                else:
                    processed_content = processed_content + profile_context
                    # Include GitHub/social context in validation source so correctly inferred
                    # skills from repos (e.g. "Python" from GitHub languages) are not rejected
                    original_source_text = original_source_text + "\n" + profile_context

            ai_response = generate_resume(
                source_type=source_type,
                content=processed_content,
                additional_instructions=additional_instructions if source_type != 'combined' else "",
                has_github_context=has_github_context,
                has_social_url=has_social_url,
            )
        except Exception as e:
            logger.error(f"[Task {task_id}] AI API error: {e}")
            raise ResumeGenerationTaskError(
                _("Failed to connect to AI service. Please try again later.")
            )

        # Map AI response to database entities
        logger.info(f"[Task {task_id}] Mapping AI response to database entities")
        try:
            # Skills the platform does not stock yet are created pending review
            # and attributed to the candidate, exactly as the skill-creation
            # endpoint does for a manual submission.
            mapped_data = map_ai_response_to_database(
                ai_response,
                source_text=original_source_text,
                created_by=_resolve_skill_author(candidate_id),
            )
        except Exception as e:
            logger.error(f"[Task {task_id}] Database mapping error: {e}")
            raise ResumeGenerationTaskError(f"Failed to map to database entities: {str(e)}")

        # Log mapping results
        mapping_metadata = mapped_data.get('mapping_metadata', {})
        skills_matched = len(mapping_metadata.get('skills_matched', []))
        skills_unmatched = len(mapping_metadata.get('skills_unmatched', []))
        skills_created = mapping_metadata.get('skills_created', [])
        logger.info(
            f"[Task {task_id}] Mapping complete: "
            f"{skills_matched} skills matched, {skills_unmatched} unmatched, "
            f"{len(skills_created)} created pending review {skills_created}"
        )

        # Auto-save the generated resume
        logger.info(f"[Task {task_id}] Saving generated resume to database")
        saved_resume = _save_generated_resume(candidate_id, mapped_data)
        logger.info(f"[Task {task_id}] Resume saved: {saved_resume.id}")

        # Update JobQueue status to completed
        if job_queue_id:
            JobQueueService.update_job_status(
                job_queue_id, "completed"
            )

        # Usage is incremented atomically in the view before enqueue, so the
        # task does not touch it — doing both double-counted.

        logger.info(f"[Task {task_id}] Resume generation completed successfully")

        return {
            'success': True,
            'data': {
                **mapped_data,
                'resume_id': str(saved_resume.id),
            },
            'error': None,
        }

    except ResumeGenerationTaskError as e:
        logger.error(f"[Task {task_id}] Task failed: {e}")
        _handle_task_failure(job_queue_id, str(e), candidate_id, source_type,
                             content, file_extension, additional_instructions,
                             retry_attempt)
        # Return error result instead of re-raising to avoid marking job as failed
        # when a retry was scheduled
        return {
            'success': False,
            'data': None,
            'error': str(e),
        }
    except Exception:
        logger.exception(f"[Task {task_id}] Unexpected error during resume generation")
        error_msg = _("An unexpected error occurred during resume generation.")
        _handle_task_failure(job_queue_id, error_msg, candidate_id, source_type,
                             content, file_extension, additional_instructions,
                             retry_attempt)
        # Return error result instead of re-raising to avoid marking job as failed
        # when a retry was scheduled
        return {
            'success': False,
            'data': None,
            'error': error_msg,
        }


def _resolve_skill_author(candidate_id: str):
    """
    The user any skills created from this resume are attributed to.

    Returns ``None`` when the candidate cannot be loaded — the mapper then
    drops unknown skills instead of creating unattributed rows, which is the
    safer failure for a table a reviewer has to work through.
    """
    from apps.authentication.models import Candidate

    try:
        return Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.warning("Candidate %s not found; skills will not be created", candidate_id)
        return None


def _save_generated_resume(candidate_id: str, mapped_data: dict):
    """
    Create Resume and all related objects from AI-generated data.

    All operations within a single transaction for atomicity.
    """
    from apps.authentication.models import Candidate
    from apps.authentication.transitions import CREATE_RESUME, update_candidate_step
    from apps.resumes.models import (
        Resume, ResumeSkill, ResumeExperience,
        ResumeCertificate, ResumeContact, ResumeLanguageCertificate,
    )
    from apps.skills.models import Skill
    from apps.languages.models import Language

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        raise ResumeGenerationTaskError(f"Candidate {candidate_id} not found")

    resume_data = mapped_data.get('resume', {})

    with transaction.atomic():
        resume = Resume.objects.create(
            candidate=candidate,
            description=resume_data.get('description', ''),
            position=resume_data.get('position', 'Software Developer'),
            domain_id=resume_data.get('domain_id'),
            work_status=resume_data.get('work_status') or 'ACTIVELY_LOOKING',
            current_company_name=resume_data.get('current_company_name'),
            current_position=resume_data.get('current_position'),
            employment_start_date=resume_data.get('employment_start_date'),
            current_salary=resume_data.get('current_salary'),
            salary_currency=resume_data.get('salary_currency') or 'UZS',
            salary_hide=resume_data.get('salary_hide', False),
            created_by_type=Resume.CreatedByType.AI_GENERATED,
            is_reviewed=False,
        )
        update_candidate_step(candidate, CREATE_RESUME)

        # Create skills
        for skill_entry in resume_data.get('skills_data', []):
            skill_id = skill_entry.get('skill_id')
            if skill_id:
                try:
                    skill = Skill.objects.get(id=skill_id)
                    ResumeSkill.objects.create(
                        resume=resume,
                        skill=skill,
                        proficiency_level=skill_entry.get('proficiency_level', 'UNDEFINED'),
                        minimum_years=skill_entry.get('minimum_years', 0),
                    )
                except Skill.DoesNotExist:
                    logger.warning(f"Skill {skill_id} not found, skipping")

        # Create experiences
        for exp in resume_data.get('experiences_data', []):
            if exp.get('company') and exp.get('role'):
                ResumeExperience.objects.create(
                    resume=resume,
                    company=exp.get('company', ''),
                    role=exp.get('role', ''),
                    country=exp.get('country') or '',
                    city=exp.get('city') or '',
                    start_date=exp.get('start_date'),
                    end_date=exp.get('end_date'),
                    description=exp.get('description') or '',
                )

        # Create certificates (metadata only, no file)
        for cert in resume_data.get('certificates_data', []):
            if cert.get('name'):
                ResumeCertificate.objects.create(
                    resume=resume,
                    name=cert.get('name'),
                    issuing_organization=cert.get('issuing_organization'),
                    issue_date=cert.get('issue_date'),
                    expiration_date=cert.get('expiration_date'),
                    credential_id=cert.get('credential_id'),
                    credential_url=cert.get('credential_url'),
                )

        # Create candidate profile contacts
        candidate_profile = mapped_data.get('candidate_profile', {})
        contact_map = {
            'email': ('EMAIL', candidate_profile.get('email')),
            'phone': ('PHONE', candidate_profile.get('phone')),
            'linkedin': ('LINKEDIN', candidate_profile.get('linkedin')),
            'github': ('GITHUB', candidate_profile.get('github')),
            'portfolio': ('PORTFOLIO', candidate_profile.get('portfolio')),
        }
        for contact_type, (type_code, contact_value) in contact_map.items():
            if contact_value:
                ResumeContact.objects.create(
                    resume=resume,
                    type=type_code,
                    value=str(contact_value),
                )

        # Create language certificates
        for lang_entry in resume_data.get('language_certificates_data', []):
            lang_id = lang_entry.get('language_id')
            if lang_id:
                try:
                    language = Language.objects.get(id=lang_id)
                    ResumeLanguageCertificate.objects.create(
                        resume=resume,
                        language=language,
                        level=lang_entry.get('level', 'A1'),
                    )
                except Language.DoesNotExist:
                    logger.warning(f"Language {lang_id} not found, skipping")

        # ponytail: update_candidate_step already called after resume creation above.
        # Second call is redundant — step is already set.

    return resume


def _handle_task_failure(
    job_queue_id: Optional[str],
    error_message: str,
    candidate_id: str,
    source_type: str,
    content: str,
    file_extension: Optional[str],
    additional_instructions: str,
    retry_attempt: int,
):
    """
    Update JobQueue status to FAILED and re-enqueue if within retry limit.
    """
    from apps.general.models import JobQueue

    if not job_queue_id:
        return

    try:
        job = JobQueue.objects.get(id=job_queue_id)
    except JobQueue.DoesNotExist:
        return

    should_retry = job.can_retry
    job.mark_failed(error_message)

    if should_retry:
        queue = django_rq.get_queue('default')
        queue.enqueue(
            process_resume_generation,
            candidate_id=candidate_id,
            source_type=source_type,
            content=content,
            file_extension=file_extension,
            additional_instructions=additional_instructions,
            job_timeout=300,
            job_queue_id=job_queue_id,
            retry_attempt=retry_attempt + 1,
        )
        logger.info(
            f"Re-enqueued resume generation retry {retry_attempt + 1} "
            f"for candidate {candidate_id}"
        )
