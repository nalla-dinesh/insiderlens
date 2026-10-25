"""GET /api/evaluation/{run_id} + /api/evaluation/compare — Phase 07.

Everything here is read-only evidence math: the run's alerts ↔ ground_truth
overlap, scenario verdicts, and target gates. Unknown run → 404 (AppError)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.evaluation import CompareReport, EvaluationReport
from app.services.evaluation import EvaluationService, evaluate_cached

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/compare", response_model=CompareReport)
async def compare_runs(
    session: DbSession,
    run_a: int = Query(..., description="baseline run id"),
    run_b: int = Query(..., description="tuned run id"),
) -> CompareReport:
    """Side-by-side metrics for tuning iterations (both full JSON + deltas).
    No caching here: compare is a deliberate live read."""
    if run_a == run_b:
        raise AppError(
            code="same_run_compare",
            message="run_a and run_b must differ — a run cannot be tuned against itself.",
            status_code=422,
        )
    return await EvaluationService(session).compare(run_a, run_b)


@router.get("/{run_id}", response_model=EvaluationReport)
async def evaluate_run(run_id: int, session: DbSession) -> EvaluationReport:
    return await evaluate_cached(session, run_id)
