"""LLM Provider abstraction layer."""

from abc import ABC, abstractmethod
from typing import Optional

import os

import openai
from openai import OpenAI
from groq import Groq

from research_digest.llm.rate_limiter import RateLimiter, RateLimitedLLMProvider


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text from the LLM."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: Optional[str] = None):
        self.client = OpenAI(api_key=api_key)
        if base_url:
            self.client.base_url = base_url
        self.model = model
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text using OpenAI API."""
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
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = Groq(api_key=api_key)
        self.model = model
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text using Groq API."""
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
    
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text using Ollama API."""
        import requests
        
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        
        if system_prompt:
            data["system"] = system_prompt
        
        try:
            response = requests.post(f"{self.base_url}/api/generate", json=data, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except Exception as e:
            raise RuntimeError(f"Ollama API error: {e}")


def create_llm_provider(config):
    """Factory function to create LLM provider based on config."""
    # Create the base provider
    if config.llm.provider.lower() == "openai":
        if not config.llm.api_key:
            raise ValueError("OpenAI API key is required")
        base_provider = OpenAIProvider(
            api_key=config.llm.api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
        )
    elif config.llm.provider.lower() == "groq":
        api_key = config.llm.api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("Groq API key is required")
        base_provider = GroqProvider(
            api_key=api_key,
            model=config.llm.model or "llama-3.3-70b-versatile",
        )
    elif config.llm.provider.lower() == "ollama":
        base_provider = OllamaProvider(
            model=config.llm.model,
            base_url=config.llm.base_url or "http://localhost:11434",
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")
    
    # Apply rate limiting if enabled
    if config.app.rate_limit.enabled:
        rate_limiter = RateLimiter(max_requests_per_minute=config.app.rate_limit.max_requests_per_minute)
        return RateLimitedLLMProvider(
            base_provider, 
            rate_limiter,
            enable_backoff=config.app.rate_limit.enable_backoff,
            max_backoff_time=config.app.rate_limit.max_backoff_time
        )
    else:
        return base_provider