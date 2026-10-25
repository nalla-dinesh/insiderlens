"""Export routes — GET (curl-friendly, no graph image) + POST (frontend attaches
the Cytoscape canvas PNG as a base64 dataURL in the JSON body; HTTP query
strings cannot safely carry multi-MB payloads through most stacks)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.export import build_case_zip_response

router = APIRouter(prefix="/api/cases", tags=["export"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


class ExportRequest(BaseModel):
    graph_png: str | None = Field(default=None, description="dataURL from cy.png()")


@router.get("/{case_id}/export", summary="Evidence ZIP (no graph image; text fallback in PDF)")
async def export_case(case_id: int, session: DbSession):  # noqa: ANN201 - StreamingResponse
    return await build_case_zip_response(session, case_id, None)


@router.post("/{case_id}/export", summary="Evidence ZIP with graph canvas PNG embedded")
async def export_case_with_graph(case_id: int, body: ExportRequest, session: DbSession):  # noqa: ANN201,E501
    return await build_case_zip_response(session, case_id, body.graph_png)
