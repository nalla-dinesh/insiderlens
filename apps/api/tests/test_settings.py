"""Settings edge cases — regression tests for the Phase-00 dotenv bug:

pydantic-settings JSON-decodes complex fields (list[...]) read from dotenv,
so CORS_ORIGINS=http://a,http://b must NOT crash Settings construction.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_cors_origins_from_dotenv_comma_string(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("CORS_ORIGINS=http://localhost:5173, http://example.com\n", encoding="utf-8")
    settings = Settings(_env_file=str(env_file))  # type: ignore[call-arg]  # pydantic-settings kwarg
    assert settings.cors_origin_list == ["http://localhost:5173", "http://example.com"]


def test_cors_origin_list_property_splits_and_trims() -> None:
    settings = Settings(cors_origins="http://a,http://b , ,")
    assert settings.cors_origin_list == ["http://a", "http://b"]


def test_database_url_rejects_sync_dialect() -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        Settings(database_url="postgresql://user:pw@localhost:5432/db")
