"""Detection pipeline endpoints — POST run + runs list."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.repositories import alerts_repo
from app.schemas.alerts import AnalysisReport, RunList, RunSummary
from app.services.pipeline import run_analysis
from app.services.rules_config import RulesConfig, get_rules_config

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _rules(request: Request) -> RulesConfig:
    return get_rules_config(str(request.app.state.settings.rules_config))


def _rules_path(request: Request) -> str:
    return str(request.app.state.settings.rules_config)


Rules = Annotated[RulesConfig, Depends(_rules)]
RulesPath = Annotated[str, Depends(_rules_path)]


@router.post("/run", response_model=AnalysisReport)
async def run_pipeline(session: DbSession, cfg: Rules, rules_path: RulesPath) -> AnalysisReport:
    """Full detection run over the ingested bundle (seconds on 50k rows);
    every run — success or failure — leaves a RUNS row an analyst can audit."""
    try:
        report = await run_analysis(session, cfg, rules_path)
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001 - run row is FAILED already; loud 500
        raise AppError(
            code="analysis_run_failed",
            message=f"Analysis run failed: {type(e).__name__}: {e}",
            status_code=500,
        ) from e
    return AnalysisReport(**report)


@router.get("/runs", response_model=RunList)
async def list_runs(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunList:
    rows, total = await alerts_repo.list_runs(session, limit, offset)
    return RunList(items=[RunSummary.model_validate(r) for r in rows], total=total)
