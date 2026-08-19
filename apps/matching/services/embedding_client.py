import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Simple client for internal embedding service."""

    @staticmethod
    def embed_text(text, translate=True):
        """Get embedding for single text."""
        try:
            url = f"{settings.EMBEDDING_SERVICE_URL}/embed"
            response = requests.post(
                url, json={"text": text, "translate": translate}, timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Embedding service error: {e}")
            raise

    @staticmethod
    def embed_batch(texts, translate=True):
        """Get embeddings for multiple texts."""
        try:
            url = f"{settings.EMBEDDING_SERVICE_URL}/embed/batch"
            response = requests.post(
                url, json={"texts": texts, "translate": translate}, timeout=120
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Embedding batch error: {e}")
            raise
