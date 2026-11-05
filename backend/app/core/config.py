"""Application configuration loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "API COMPASS"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://postgres:postgres@localhost:5432/api_compass")
    )
    db_connect_timeout_seconds: float = 3.0

    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:3000"

    # Supabase project URL. Access tokens are verified against its public signing keys.
    supabase_url: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def _force_asyncpg_driver(cls, value: object) -> object:
        # Hosted providers (Supabase, Render) hand out plain postgres:// URLs.
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
