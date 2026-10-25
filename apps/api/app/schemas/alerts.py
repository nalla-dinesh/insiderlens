"""Pydantic DTOs for runs/alerts/timeline (Phase 04)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AlertStatus = Literal["OPEN", "ACKNOWLEDGED", "IN_REVIEW", "RESOLVED", "DISMISSED"]
ALLOWED_STATUSES: list[str] = ["OPEN", "ACKNOWLEDGED", "IN_REVIEW", "RESOLVED", "DISMISSED"]


class ReasonItem(BaseModel):
    rule: str
    pts: int
    text: str


class AlertSummary(BaseModel):
    """List-row: reasons ride WITH the score (the UI never shows number alone)."""

    model_config = ConfigDict(from_attributes=True)

    alert_id: int
    run_id: int
    band: str
    score: int
    rule_set: list[str]
    entity_ids: list[int]
    entity_type: str
    status: str
    created_at: datetime
    top_reasons: list[str]  # top-2 reason texts
    case_id: int | None = None  # Phase 06: which case owns this alert (null = unlinked)
    max_amount: float | None = None  # largest cited txn leg — dashboard Amount column
    entity_counts: dict[str, int] = {}  # {"accounts": n, "employees": m} — dashboard Entities column


class AlertDetail(AlertSummary):
    reasons: list[ReasonItem]
    evidence: dict[str, Any]


class AlertPage(BaseModel):
    items: list[AlertSummary]
    total: int
    limit: int
    offset: int
    band_counts: dict[str, int]  # per-band counts under current filters (Phase 05 header cards)


class AlertStatusPatch(BaseModel):
    status: AlertStatus


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    started_at: datetime
    finished_at: datetime | None
    txn_count: int | None
    alert_count: int | None
    status: str
    config: dict[str, Any]


class RunList(BaseModel):
    items: list[RunSummary]
    total: int


class AnalysisReport(BaseModel):
    run_id: int
    status: str
    alerts_by_band: dict[str, int]
    duration_ms: int
    per_rule_hits: dict[str, int]
    signals_dropped: int
    errors: list[str]
