import logging
from .embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)


def generate_vacancy_embedding_task(vacancy_id):
    """Generate embedding for a vacancy via external service."""
    from apps.vacancies.models import Vacancy

    try:
        vacancy = Vacancy.objects.get(id=vacancy_id)
        text_to_embed = vacancy.get_text_for_embedding()

        if not text_to_embed.strip():
            logger.warning(f"No text to embed for vacancy {vacancy_id}")
            return False

        logger.info(f"Processing vacancy: {vacancy.title}")

        # Use the client
        result = EmbeddingClient.embed_text(text_to_embed, translate=True)

        # Save to database
        vacancy.combined_text_en = result["translated_text"]
        vacancy.embedding = result["embedding"]
        vacancy.is_embedded = True
        vacancy.save(update_fields=["combined_text_en", "embedding", "is_embedded"])

        logger.info(f"Embedding generated for vacancy {vacancy_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to generate embedding for vacancy {vacancy_id}: {e}")
        return False


def generate_resume_embedding_task(resume_id):
    """Generate embedding for a resume via external service."""
    from apps.resumes.models import Resume

    try:
        resume = Resume.objects.get(id=resume_id)
        text_to_embed = resume.get_text_for_embedding()

        if not text_to_embed.strip():
            logger.warning(f"No text to embed for resume {resume_id}")
            return False

        logger.info(f"Processing resume: {resume.title}")

        # Use the client
        result = EmbeddingClient.embed_text(text_to_embed, translate=True)

        # Save to database
        resume.combined_text_en = result["translated_text"]
        resume.embedding = result["embedding"]
        resume.is_embedded = True
        resume.save(update_fields=["combined_text_en", "embedding", "is_embedded"])

        logger.info(f"Embedding generated for resume {resume_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to generate embedding for resume {resume_id}: {e}")
        return False
