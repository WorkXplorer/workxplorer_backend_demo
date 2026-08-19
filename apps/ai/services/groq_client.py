"""
Generic Groq Cloud API client.

Provides a reusable client for chat completions via the Groq API,
decoupled from any specific business domain (resumes, skill validation, etc.).
"""

import logging
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache as django_cache

from apps.ai.services.ai_utils import build_cache_key, parse_json_response, strip_code_fence

logger = logging.getLogger(__name__)


class GroqClient:
    """Generic client for Groq Cloud chat completions."""

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self._api_key = None
        self._model = None

    @property
    def api_key(self) -> str:
        if self._api_key is None:
            self._api_key = getattr(settings, "GROQ_API_KEY", None)
            if not self._api_key:
                raise ValueError("GROQ_API_KEY is not configured in settings.")
        return self._api_key

    @property
    def model(self) -> str:
        if self._model is None:
            self._model = getattr(settings, "GROQ_MODEL", "qwen/qwen3-32b")
        return self._model

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0,
        json_mode: bool = False,
        timeout: int = 120,
    ) -> dict[str, Any]:
        """
        Send a chat completion request to Groq API.

        Args:
            messages: List of message dicts with "role" and "content".
            temperature: Sampling temperature (0 = deterministic).
            json_mode: If True, request JSON response format.
            timeout: Request timeout in seconds.

        Returns:
            Parsed API response dict containing "choices" and "usage".

        Raises:
            requests.RequestException: On HTTP/network errors.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            # Disable reasoning for structured output — faster, cheaper
            payload["reasoning_effort"] = "none"
            payload["reasoning_format"] = "hidden"

        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            sanitized_msg = str(e).replace(self.api_key, "***REDACTED***")
            logger.error("Groq API request failed: %s", sanitized_msg)
            raise requests.RequestException(sanitized_msg) from e
        response_json = response.json()

        self._log_usage(response_json)

        return response_json

    def cached_completion(
        self,
        messages: list[dict[str, str]],
        cache_key_prefix: str,
        *cache_params: str,
        temperature: float = 0,
        json_mode: bool = False,
        timeout: int = 120,
    ) -> dict[str, Any]:
        """
        Chat completion with Redis caching.

        Caches successful responses keyed by a hash of all input parameters.
        """
        cache_key = self._build_cache_key(cache_key_prefix, *cache_params)
        cached = django_cache.get(cache_key)
        if cached is not None:
            logger.info("Groq cache HIT: %s", cache_key)
            return cached

        logger.info("Groq cache MISS: %s", cache_key)
        result = self.chat_completion(
            messages, temperature=temperature, json_mode=json_mode, timeout=timeout
        )

        ttl = getattr(settings, "AI_RESPONSE_CACHE_TIMEOUT", 60 * 60 * 24)
        django_cache.set(cache_key, result, timeout=ttl)
        logger.info("Groq response cached: %s", cache_key)
        return result

    _build_cache_key = staticmethod(build_cache_key)

    @staticmethod
    def _log_usage(response_json: dict[str, Any]) -> None:
        usage = response_json.get("usage", {})
        if not usage:
            return
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        cached_tokens = (
            usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        )
        logger.info(
            "Groq API usage: prompt=%d, completion=%d, total=%d, cached=%d",
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cached_tokens,
        )

    strip_code_fence = staticmethod(strip_code_fence)
    parse_json_response = staticmethod(parse_json_response)
