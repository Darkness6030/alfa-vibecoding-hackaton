"""Application configuration.

Settings are read from environment variables with sane defaults so the same
image can run under different profiles (see docs/decisions.md D07).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ALFAGEN_", env_file=".env", extra="ignore")

    app_name: str = "alfagen-pii-guard"
    profile: str = "evaluation-open"
    log_level: str = "INFO"

    # Placeholder engine flag. Real detectors arrive in K3/K4; until then the
    # engine is an explicitly marked stub that must not be presented as masking.
    engine_stub: bool = True

    # Redis state (D05). Redis is shared across workers for consistent state.
    redis_url: str = "redis://localhost:6379/0"
    state_namespace: str = "evaluation-open"
    state_consumer: str = "stand"
    state_ttl_seconds: int = 900  # 15 minutes
    state_max_record_bytes: int = 1_000_000  # per-record payload limit

    # Encryption key for reversible mappings (D07). Must be shared across
    # workers. If empty, an ephemeral key is generated at startup (dev only:
    # mappings are lost on restart).
    encryption_key: str = ""

    # Concurrency limit: when exceeded, /process returns 429 with Retry-After.
    max_concurrency: int = 100


settings = Settings()