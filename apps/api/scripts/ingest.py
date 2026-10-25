"""CLI: load the Phase-01 bundle into Postgres.

    python scripts/ingest.py [--data-dir ../../data/generated]

Exits 0 on success (report printed), 2 on failure. `make ingest` wraps this.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.config import get_settings
from app.db.session import build_engine, build_session_factory
from app.schemas.ingest import IngestReport
from app.services.ingestion import IngestionService


def _print(report: IngestReport) -> None:
    print(f"\ningest report  (checksum_ok={report.checksum_ok}, dir={report.data_dir})")
    print(f"  {'table':<14} {'rows':>8} {'inserted':>9} {'skipped':>8} {'ms':>6}")
    for name, t in report.tables.items():
        print(f"  {name:<14} {t.rows_in_csv:>8,} {t.inserted:>9,} {t.skipped:>8,} {t.duration_ms:>6}")
    print(
        f"  {'TOTAL':<14} {report.total_rows:>8,} {report.total_inserted:>9,} {'':>8} {report.duration_ms:>6}"
    )


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir", type=Path, default=Path(__file__).resolve().parents[3] / "data" / "generated"
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        service = IngestionService(build_session_factory(engine), args.data_dir)
        report = await service.run()
        _print(report)
        return 0
    except Exception as e:  # noqa: BLE001 - CLI boundary: print and exit 2
        print(f"[ingest FAILED] {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
