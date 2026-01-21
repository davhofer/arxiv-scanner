"""Configuration management using Pydantic settings."""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    provider: str = Field(default="openai", description="LLM provider: openai or ollama")
    model: str = Field(default="gpt-4o-mini", description="Model name")
    api_key: Optional[str] = Field(default=None, description="API key for commercial providers")
    base_url: Optional[str] = Field(default=None, description="Custom base URL for provider")


class AppConfig(BaseModel):
    throttling_delay: float = Field(default=3.0, description="Seconds to wait between topics")
    db_path: str = Field(default="research.db", description="Path to SQLite database")


class Config(BaseSettings):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    app: AppConfig = Field(default_factory=AppConfig)

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        env_prefix = "RD_"

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