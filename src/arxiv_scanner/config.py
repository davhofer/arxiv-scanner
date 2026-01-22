"""Configuration management using Pydantic settings."""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = Field(
        default="groq", description="LLM provider: groq, openai, or ollama"
    )
    model: str = Field(default="llama-3.3-70b-versatile", description="Model name")
    api_key: Optional[str] = Field(
        default=None, description="API key for commercial providers"
    )
    base_url: Optional[str] = Field(
        default=None, description="Custom base URL for provider"
    )


class RateLimitConfig(BaseModel):
    enabled: bool = Field(default=True, description="Enable intelligent rate limiting")
    max_requests_per_minute: float = Field(
        default=20.0, description="Maximum LLM requests per minute"
    )
    enable_backoff: bool = Field(
        default=True, description="Enable exponential backoff for rate limit errors"
    )
    max_backoff_time: float = Field(
        default=60.0, description="Maximum backoff time in seconds"
    )


class AppConfig(BaseModel):
    throttling_delay: float = Field(
        default=3.0,
        description="Seconds to wait between topics (deprecated, use rate_limiting)",
    )
    db_path: str = Field(default="papers.db", description="Path to SQLite database")
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)


class Config(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    app: AppConfig = Field(default_factory=AppConfig)

    @classmethod
    def load_from_file(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path("config.yaml")

        if not config_path.exists():
            return cls()

        try:
            import yaml

            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f)
            return cls(**config_data)
        except ImportError:
            raise ImportError("PyYAML is required to load config from YAML file")
        except Exception as e:
            raise ValueError(f"Failed to load config from {config_path}: {e}")
