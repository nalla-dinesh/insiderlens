"""v0 account reads — the Phase 05 frontend's first data source."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.repositories import accounts_repo
from app.schemas.accounts import AccountOut, AccountPage

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=AccountPage)
async def list_accounts(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountPage:
    rows, total = await accounts_repo.list_accounts(session, limit, offset)
    return AccountPage(
        items=[AccountOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{acc_id}", response_model=AccountOut)
async def get_account(acc_id: int, session: DbSession) -> AccountOut:
    row = await accounts_repo.get_account(session, acc_id)
    if row is None:
        raise AppError(
            code="account_not_found",
            message=f"Account {acc_id} does not exist.",
            status_code=404,
            details={"acc_id": acc_id},
        )
    return AccountOut.model_validate(row)
