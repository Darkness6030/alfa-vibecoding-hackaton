"""Environment configuration; invalid profiles and non-positive limits fail closed."""

from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALFAGEN_", env_file=".env", extra="ignore"
    )
    app_name: str = "alfagen-pii-guard"
    profile: Literal["evaluation-open", "demo-secure"] = "evaluation-open"
    log_level: str = "INFO"
    engine_stub: bool = False
    ner_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    state_namespace: str = "evaluation-open"
    state_consumer: str = "stand"
    state_ttl_seconds: int = Field(default=900, ge=1, le=86400)
    state_max_record_bytes: int = Field(default=16_000_000, ge=1024)
    max_body_bytes: int = Field(default=8_000_000, ge=1024)
    encryption_key: str = ""
    max_concurrency: int = Field(default=32, ge=1)
    policy_file: str = ""
    metrics_api_key: str = ""


settings = Settings()
