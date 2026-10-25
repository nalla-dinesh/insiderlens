"""Central settings — env-driven, validated once at startup.

NOTES
- `database_url` is deliberately `str`, not pydantic's PostgresDsn: SQLAlchemy-async
  needs the `postgresql+asyncpg://` dialect scheme, which PostgresDsn rejects.
  We validate the shape ourselves — startup must fail fast on garbage.
- `ENV` (team convention) or `ENVIRONMENT` both feed `environment`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    project_name: str = "InsiderLens"
    version: str = "0.1.0"
    environment: Literal["development", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("ENV", "ENVIRONMENT"),
    )

    database_url: str = "postgresql+asyncpg://insider:insider@localhost:5432/insiderlens"
    rules_config: Path = Path("infra/config/rules.yaml")
    # Where the SEEDED demo bundle lives (S5 showcase tests); None -> tests skip
    seed_database_url: str | None = None

    # Deliberately a plain `str`, NOT list[str]: pydantic-settings JSON-decodes
    # complex fields read from dotenv/env, so list[str] here CRASHES on the
    # human-friendly format CORS_ORIGINS=http://a,http://b
    # (real bug caught on a Windows laptop during Phase 00 — fixed via str + property;
    # regression test: tests/test_settings.py::test_cors_origins_from_dotenv_comma_string)
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def _must_be_asyncpg(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the postgresql+asyncpg:// dialect "
                "(plain postgresql:// breaks async SQLAlchemy) — prompt pitfall P1"
            )
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS env arrives as one comma-joined string -> clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
