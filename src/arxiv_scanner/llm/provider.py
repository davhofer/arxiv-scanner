"""LLM Provider abstraction layer."""

import os
import time
from abc import ABC, abstractmethod
from typing import Optional

from openai import OpenAI
from groq import Groq


class LLMProvider(ABC):
    """Abstract base class for LLM providers with built-in rate limiting."""

    def __init__(self, requests_per_minute: float = 0):
        self.min_interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0
        self.last_request_time = 0.0

    def _wait_for_rate_limit(self):
        """Simple throttling to respect rate limits."""
        if self.min_interval > 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request_time = time.time()

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text from the LLM."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        requests_per_minute: float = 0,
    ):
        super().__init__(requests_per_minute)
        self.client = OpenAI(api_key=api_key)
        if base_url:
            self.client.base_url = base_url
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text using OpenAI API."""
        self._wait_for_rate_limit()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")


class GroqProvider(LLMProvider):
    """Groq API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        requests_per_minute: float = 0,
    ):
        super().__init__(requests_per_minute)
        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text using Groq API."""
        self._wait_for_rate_limit()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as e:
            raise RuntimeError(f"Groq API error: {e}")


class OllamaProvider(LLMProvider):
    """Ollama local model provider."""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        requests_per_minute: float = 0,
    ):
        super().__init__(requests_per_minute)
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text using Ollama API."""
        import requests

        self._wait_for_rate_limit()

        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            data["system"] = system_prompt

        try:
            response = requests.post(
                f"{self.base_url}/api/generate", json=data, timeout=60
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except Exception as e:
            raise RuntimeError(f"Ollama API error: {e}")


def create_llm_provider(config):
    """Factory function to create LLM provider based on config."""

    rpm = (
        config.app.rate_limit.max_requests_per_minute
        if config.app.rate_limit.enabled
        else 0
    )

    if config.llm.provider.lower() == "openai":
        api_key = config.llm.api_key or os.environ.get("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OpenAI API key is required in config or OPENAI_API_KEY env var"
            )

        return OpenAIProvider(
            api_key=api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
            requests_per_minute=rpm,
        )

    elif config.llm.provider.lower() == "groq":
        api_key = config.llm.api_key or os.environ.get("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "Groq API key is required in config or GROQ_API_KEY env var"
            )

        return GroqProvider(
            api_key=api_key,
            model=config.llm.model or "llama-3.3-70b-versatile",
            requests_per_minute=rpm,
        )

    elif config.llm.provider.lower() == "ollama":
        return OllamaProvider(
            model=config.llm.model,
            base_url=config.llm.base_url or "http://localhost:11434",
            requests_per_minute=rpm,
        )

    else:
        raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")
