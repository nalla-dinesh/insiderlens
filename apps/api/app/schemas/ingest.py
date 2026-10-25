"""Ingestion report DTOs — returned by POST /api/ingest and printed by scripts/ingest.py."""

from pydantic import BaseModel


class TableIngestStat(BaseModel):
    rows_in_csv: int
    inserted: int
    skipped: int  # already present (idempotent re-run)
    duration_ms: int


class IngestReport(BaseModel):
    data_dir: str
    checksum_ok: bool
    tables: dict[str, TableIngestStat]
    total_rows: int
    total_inserted: int
    duration_ms: int
