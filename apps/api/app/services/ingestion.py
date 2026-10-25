"""CSV bundle -> Postgres. Idempotent by construction (natural-PK upserts),
checksum-guarded by meta.json, one transaction per run, per-table reporting.

LAW: detection services may never read ground_truth — only THIS ingestion module
and Phase 07's EvaluationService may touch its rows.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.account import Account
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.employee import Employee, Role
from app.models.ground_truth import GroundTruth
from app.models.transaction import Transaction
from app.repositories.ingestion_repo import bulk_insert_idempotent
from app.schemas.ingest import IngestReport, TableIngestStat

logger = get_logger(__name__)


def _ts(v: str) -> datetime:
    """'2026-07-01T10:30:00Z' -> tz-aware UTC (P3: asyncpg wants tz-aware)."""
    return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _d(v: str) -> date:
    return date.fromisoformat(v)


def _b(v: str) -> bool:
    return v.strip().lower() in ("true", "1", "yes")


def _opt_int(v: str) -> int | None:
    v = v.strip()
    return int(Decimal(v)) if v else None  # tolerant: "1017" and legacy "1017.00" both fine


def _opt_str(v: str) -> str | None:
    v = v.strip()
    return v if v else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IngestionService:
    ORDER = ["roles", "employees", "customers", "accounts", "transactions", "activity_log", "ground_truth"]

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], data_dir: Path) -> None:
        self.session_factory = session_factory
        self.data_dir = Path(data_dir)

    # ---------- row readers ----------
    def _rows(self, name: str) -> list[dict[str, str]]:
        path = self.data_dir / f"{name}.csv"
        if not path.exists():
            raise AppError(
                code="ingest_source_missing",
                message=f"{path} not found — run the generator first (Phase 01)",
                status_code=409,
            )
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def _transform(self, name: str, raw: dict[str, str]) -> dict:
        if name == "roles":
            return {
                "role_name": raw["role_name"],
                "allowed_actions": [a for a in raw["allowed_actions"].split("|") if a],
                "description": raw["description"],
            }
        if name == "employees":
            return {
                "emp_id": int(raw["emp_id"]),
                "name": raw["name"],
                "role": raw["role"],
                "branch": raw["branch"],
                "join_date": _d(raw["join_date"]),
                "status": raw["status"],
            }
        if name == "customers":
            return {
                "cust_id": int(raw["cust_id"]),
                "name": raw["name"],
                "occupation": raw["occupation"],
                "declared_income": Decimal(raw["declared_income"]),
                "kyc_risk": raw["kyc_risk"],
                "phone": raw["phone"],
                "address": raw["address"],
            }
        if name == "accounts":
            return {
                "acc_id": int(raw["acc_id"]),
                "cust_id": int(raw["cust_id"]),
                "type": raw["type"],
                "branch": raw["branch"],
                "open_date": _d(raw["open_date"]),
                "last_active_date": _d(raw["last_active_date"]),
                "status": raw["status"],
            }
        if name == "transactions":
            return {
                "txn_id": int(raw["txn_id"]),
                "from_acc": int(raw["from_acc"]),
                "to_acc": int(raw["to_acc"]),
                "amount": Decimal(raw["amount"]),
                "ts": _ts(raw["ts"]),
                "channel": raw["channel"],
                "purpose": _opt_str(raw["purpose"]),
                "approved_by": _opt_int(raw["approved_by"]),
            }
        if name == "activity_log":
            return {
                "log_id": int(raw["log_id"]),
                "emp_id": int(raw["emp_id"]),
                "ts": _ts(raw["ts"]),
                "action": raw["action"],
                "target_acc": _opt_int(raw["target_acc"]),
                "details": json.loads(raw["details"]),
                "ip": raw["ip"],
                "device": raw["device"],
                "off_hours": _b(raw["off_hours"]),
                "role_violation": _b(raw["role_violation"]),
            }
        if name == "ground_truth":
            return {
                "gt_id": int(raw["gt_id"]),
                "scenario_id": raw["scenario_id"],
                "entity_type": raw["entity_type"],
                "entity_ids": [int(raw["entity_ids"])],  # single-id string -> INT[]
                "is_suspicious": _b(raw["is_suspicious"]),
            }
        raise AppError(code="ingest_unknown_table", message=f"no loader for {name}", status_code=500)

    MODELS = {
        "roles": Role,
        "employees": Employee,
        "customers": Customer,
        "accounts": Account,
        "transactions": Transaction,
        "activity_log": ActivityLog,
        "ground_truth": GroundTruth,
    }

    # ---------- integrity ----------
    def _verify_checksums(self) -> bool:
        meta_path = self.data_dir / "meta.json"
        if not meta_path.exists():
            raise AppError(
                code="ingest_meta_missing",
                message=f"{meta_path} missing — regenerate the bundle (Phase 01)",
                status_code=409,
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for name in self.ORDER:
            want = meta["files"][name]["sha256"]
            got = _sha256(self.data_dir / f"{name}.csv")
            if got != want:
                raise AppError(
                    code="checksum_mismatch",
                    message=f"{name}.csv sha256 mismatch "
                    f"(expected {want[:12]}…, got {got[:12]}…) — "
                    "bundle modified or truncated; rebuild with the generator",
                    status_code=409,
                )
        return True

    # ---------- main ----------
    async def run(self) -> IngestReport:
        started = time.perf_counter()
        checksum_ok = self._verify_checksums()
        tables: dict[str, TableIngestStat] = {}

        async with self.session_factory() as session:
            async with session.begin():
                for name in self.ORDER:
                    t0 = time.perf_counter()
                    raw_rows = self._rows(name)
                    rows = [self._transform(name, r) for r in raw_rows]
                    inserted, skipped = await bulk_insert_idempotent(session, self.MODELS[name], rows)
                    ms = int((time.perf_counter() - t0) * 1000)
                    tables[name] = TableIngestStat(
                        rows_in_csv=len(rows), inserted=inserted, skipped=skipped, duration_ms=ms
                    )
                    logger.info(
                        "ingested_table",
                        table=name,
                        rows=len(rows),
                        inserted=inserted,
                        skipped=skipped,
                        duration_ms=ms,
                    )

        duration_ms = int((time.perf_counter() - started) * 1000)
        report = IngestReport(
            data_dir=str(self.data_dir),
            checksum_ok=checksum_ok,
            tables=tables,
            total_rows=sum(t.rows_in_csv for t in tables.values()),
            total_inserted=sum(t.inserted for t in tables.values()),
            duration_ms=duration_ms,
        )
        logger.info("ingest_complete", total_inserted=report.total_inserted, duration_ms=duration_ms)
        return report
