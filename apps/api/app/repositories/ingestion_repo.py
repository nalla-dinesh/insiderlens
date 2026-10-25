"""Bulk ingestion inserts.

Pattern: insert(list_of_dicts).on_conflict_do_nothing() on the natural PK —
rows carry ids from the CSVs (P2 law: never regenerate), so a re-run inserts 0.
asyncpg reports inserted-row counts in result.rowcount with ON CONFLICT DO NOTHING.
"""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

CHUNK = 2_000


async def bulk_insert_idempotent(
    session: AsyncSession, model: type[Base], rows: list[dict]
) -> tuple[int, int]:
    """Returns (inserted, skipped)."""
    inserted = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        result = await session.execute(insert(model).values(chunk).on_conflict_do_nothing())
        inserted += result.rowcount if result.rowcount is not None else len(chunk)
    return inserted, len(rows) - inserted
