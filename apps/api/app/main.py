"""InsiderLens API — application factory.

Entry points:
    uvicorn app.main:create_app --factory --reload
    docker: see CMD in apps/api/Dockerfile
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIDMiddleware
from app.core.security import AnalysisRateLimitMiddleware, SecurityHeadersMiddleware, cors_prod_guard
from app.db.session import build_engine, build_session_factory
from app.routers import (
    accounts,
    alerts,
    analysis,
    cases,
    evaluation,
    export,
    graph,
    health,
    ingest,
    transactions,
)
from app.services.rules_config import get_rules_config

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    # Fail fast BEFORE the first request: rules.yaml must parse into RulesConfig.
    # A missing/typo'd key names itself in this error — the engine never runs
    # on unknown thresholds (golden rule).
    rules = get_rules_config(str(settings.rules_config))
    logger.info("rules_config_ok", path=str(settings.rules_config), bands=rules.scoring.bands)

    engine = build_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    logger.info("api_startup", version=settings.version, environment=settings.environment)
    yield
    await engine.dispose()
    logger.info("api_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(environment=settings.environment)

    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        lifespan=lifespan,
        # API docs are a dev tool; they stay dark in production (Phase 08 also guards this).
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )
    app.state.settings = settings
    cors_prod_guard(settings.cors_origin_list, is_production=settings.is_production)

    # Middleware (last added = outermost). Request id wraps everything we log.
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.is_production:
        # 5 analysis-runs/min/client — the most expensive POST in the system (Phase 08)
        app.add_middleware(AnalysisRateLimitMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(accounts.router)
    app.include_router(transactions.router)
    app.include_router(graph.router)
    app.include_router(analysis.router)
    app.include_router(alerts.router)
    app.include_router(alerts.timeline_router)
    app.include_router(cases.router)
    app.include_router(cases.analysts_router)
    app.include_router(export.router)
    app.include_router(evaluation.router)
    return app


if __name__ == "__main__":
    uvicorn.run("app.main:create_app", factory=True, host="0.0.0.0", port=8000, reload=True)
