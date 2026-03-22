"""Shared utilities for LLM client creation.

Provides unified provider handling for image analysis and advice generation.
"""

import os

from openai import OpenAI


class LLMClientConfig:
    """Configuration for LLM client creation.

    Handles provider selection (OpenAI/Gemini) with appropriate
    base URLs, API keys, and model names.
    """

    def __init__(self, provider: str = "openai") -> None:
        """Initialize client configuration.

        Args:
            provider: Provider to use ("openai" or "gemini")
        """
        self.provider = provider
        self.client, self.model = self._create_client()

    def _create_client(self) -> tuple[OpenAI, str]:
        """Create OpenAI client and return (client, model) tuple.

        For Gemini, uses OpenAI-compatible endpoint.

        Returns:
            Tuple of (OpenAI client, model name)
        """
        if self.provider == "openai":
            base_url = "https://api.openai.com/v1"
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            model = os.getenv("ADVICE_MODEL", "gpt-4o-mini").strip()
        elif self.provider == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            model = os.getenv("CALORIE_GEMINI_MODEL", "gemini-3.1-flash-lite-preview").strip()
        else:
            # Fallback to OpenAI
            base_url = "https://api.openai.com/v1"
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            model = os.getenv("ADVICE_MODEL", "gpt-4o-mini").strip()

        if not api_key:
            raise RuntimeError(f"{self.provider.upper()}_API_KEY is not configured")

        client = OpenAI(base_url=base_url, api_key=api_key)
        return client, model

    @staticmethod
    def get_provider_from_env(default: str = "openai") -> str:
        """Get provider from environment variable.

        Args:
            default: Default provider if not set

        Returns:
            Provider name ("openai" or "gemini")
        """
        return os.getenv("CALORIE_PROVIDER", default).strip()

    def get_model_for_purpose(self, purpose: str) -> str:
        """Get model name for a specific purpose.

        Args:
            purpose: Purpose type ("image" or "advice")

        Returns:
            Model name to use
        """
        if purpose == "image":
            if self.provider == "openai":
                return os.getenv("CALORIE_OPENAI_MODEL", "gpt-4o-mini").strip()
            else:  # gemini
                return os.getenv("CALORIE_GEMINI_MODEL", "gemini-3.1-flash-lite-preview").strip()
        else:  # advice
            if self.provider == "openai":
                return os.getenv("ADVICE_MODEL", "gpt-4o-mini").strip()
            else:  # gemini
                return os.getenv("CALORIE_GEMINI_MODEL", "gemini-3.1-flash-lite-preview").strip()
