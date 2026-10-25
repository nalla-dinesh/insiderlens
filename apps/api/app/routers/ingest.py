"""POST /api/ingest — dev-only trigger for the ingestion service.
P5: this endpoint must NOT exist in production semantics; we gate on ENV."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.config import get_settings
from app.core.errors import AppError
from app.schemas.ingest import IngestReport
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/ingest", response_model=IngestReport)
async def trigger_ingest(
    request: Request,
    data_dir: Annotated[Path | None, Query()] = None,
) -> IngestReport:
    settings = get_settings()
    if settings.is_production:
        raise AppError(
            code="forbidden_in_production",
            message="Ingestion via API is a development tool only.",
            status_code=403,
        )
    if not hasattr(request.app.state, "session_factory"):
        raise AppError(code="db_not_ready", message="Database pool is not initialised.", status_code=503)
    source = data_dir or (Path(__file__).resolve().parents[4] / "data" / "generated")
    service = IngestionService(request.app.state.session_factory, source)
    return await service.run()
