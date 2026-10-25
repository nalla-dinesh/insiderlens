"""Cases router — thin HTTP shell over services/cases.py (state machine +
sequential-case rule live in the service)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.cases import AnalystOut, CaseCreate, CasePatch, NoteCreate
from app.services import cases as svc

router = APIRouter(prefix="/api/cases", tags=["cases"])
analysts_router = APIRouter(prefix="/api/analysts", tags=["cases"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", summary="Board — cases grouped by status (5 columns)")
async def board(session: DbSession) -> dict:
    return await svc.list_board(session)


@analysts_router.get("", response_model=list[AnalystOut], summary="Analyst directory (MANAGER/ADMIN)")
async def analysts(session: DbSession) -> list[dict]:
    return await svc.list_analysts(session)


@router.post("", status_code=201, summary="Create case from alert")
async def create_case(body: CaseCreate, session: DbSession) -> dict:
    return await svc.create_from_alert(session, body)


@router.get("/{case_id}", summary="Case + linked alerts FULL payloads + notes")
async def get_case(case_id: int, session: DbSession) -> dict:
    case, alerts, notes = await svc.load_case(session, case_id)
    return svc.model_payload(case, alerts, notes)


@router.patch("/{case_id}", summary="assignee/status/title — machine enforced, 409 on closed")
async def patch_case(case_id: int, body: CasePatch, session: DbSession) -> dict:
    return await svc.patch_case(session, case_id, body)


@router.post("/{case_id}/notes", status_code=201, summary="Append an audit note")
async def add_note(case_id: int, body: NoteCreate, session: DbSession) -> dict:
    return await svc.add_note(session, case_id, body)
