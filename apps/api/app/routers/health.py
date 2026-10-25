"""Ops endpoints — intentionally NOT under /api (monitoring convention).

UptimeRobot (Phase 09) and Render health checks hit /health.
/health/db performs a real SELECT 1 with a hard 2s timeout (a lying 200 is worse
than an honest 503 — said the Phase 00 stub; now it delivers).
"""

import asyncio
import time

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import get_settings
from app.core.errors import AppError
from app.schemas.common import DbHealthResponse, HealthResponse

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.version, environment=settings.environment)


@router.get("/health/db", response_model=DbHealthResponse)
async def health_db(request: Request) -> DbHealthResponse:
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise AppError(
            code="db_not_ready",
            message="Database pool not initialised (startup incomplete).",
            status_code=503,
        )
    started = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=2.0)
    except (TimeoutError, OSError) as e:
        raise AppError(
            code="db_unavailable", message="Database unreachable within 2s timeout.", status_code=503
        ) from e
    settings = get_settings()
    return DbHealthResponse(
        status="ok",
        version=settings.version,
        environment=settings.environment,
        database="up",
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
