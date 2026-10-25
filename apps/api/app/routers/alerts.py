"""Alert endpoints — the analyst queue. Reasons ALWAYS ride with the score."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.repositories import alerts_repo
from app.schemas.alerts import ALLOWED_STATUSES, AlertDetail, AlertPage, AlertStatusPatch, AlertSummary

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _summary(
    a,
    max_amounts: dict[int, float] | None = None,
    entity_counts: dict[int, dict[str, int]] | None = None,
) -> AlertSummary:
    texts = [r.get("text", "") for r in a.reasons][:2]
    return AlertSummary(
        alert_id=a.alert_id,
        run_id=a.run_id,
        band=a.band,
        score=a.score,
        rule_set=list(a.rule_set),
        entity_ids=list(a.entity_ids),
        entity_type=a.entity_type,
        status=a.status,
        created_at=a.created_at,
        top_reasons=texts,
        case_id=a.case_id,
        max_amount=(max_amounts or {}).get(a.alert_id),
        entity_counts=(entity_counts or {}).get(a.alert_id, {}),
    )


@router.get("", response_model=AlertPage)
async def list_alerts(
    session: DbSession,
    band: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    rule: Annotated[str | None, Query()] = None,
    entity: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AlertPage:
    rows, total, band_counts, max_amounts, entity_counts = await alerts_repo.list_alerts(
        session, band, status, rule, limit, offset, entity
    )
    return AlertPage(
        items=[_summary(r, max_amounts, entity_counts) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
        band_counts=band_counts,
    )


@router.get("/{alert_id}", response_model=AlertDetail)
async def get_alert(alert_id: int, session: DbSession) -> AlertDetail:
    row = await alerts_repo.get_alert(session, alert_id)
    if row is None:
        raise AppError(
            code="alert_not_found",
            message=f"Alert {alert_id} does not exist.",
            status_code=404,
            details={"alert_id": alert_id},
        )
    base = _summary(row).model_dump()
    return AlertDetail(**base, reasons=row.reasons, evidence=row.evidence)


@router.patch("/{alert_id}/status", response_model=AlertDetail)
async def patch_alert_status(alert_id: int, patch: AlertStatusPatch, session: DbSession) -> AlertDetail:
    row = await alerts_repo.get_alert(session, alert_id)
    if row is None:
        raise AppError(
            code="alert_not_found",
            message=f"Alert {alert_id} does not exist.",
            status_code=404,
            details={"alert_id": alert_id},
        )
    row.status = patch.status
    await session.commit()
    base = _summary(row).model_dump()
    return AlertDetail(**base, reasons=row.reasons, evidence=row.evidence)


timeline_router = APIRouter(prefix="/api/timeline", tags=["alerts"])


@timeline_router.get("/{alert_id}")
async def get_alert_timeline(alert_id: int, session: DbSession) -> dict:
    """Merged chronological employee+txn events — read from the evidence stored
    at run time (ONE code path: evidence.py builds it, this endpoint serves it)."""
    row = await alerts_repo.get_alert(session, alert_id)
    if row is None:
        raise AppError(
            code="alert_not_found",
            message=f"Alert {alert_id} does not exist.",
            status_code=404,
            details={"alert_id": alert_id},
        )
    return {"alert_id": alert_id, "timeline": row.evidence.get("timeline", []), "statuses": ALLOWED_STATUSES}
