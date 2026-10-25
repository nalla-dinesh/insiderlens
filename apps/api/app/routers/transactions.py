"""v0 transaction reads for an account (direction/time-bounded)."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_db
from app.repositories import accounts_repo, transactions_repo
from app.schemas.transactions import TransactionOut, TransactionPage

router = APIRouter(prefix="/api/accounts", tags=["transactions"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{acc_id}/transactions", response_model=TransactionPage)
async def list_account_transactions(
    acc_id: int,
    session: DbSession,
    direction: Literal["in", "out", "both"] = "both",
    ts_from: Annotated[datetime | None, Query(alias="from")] = None,
    ts_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    if await accounts_repo.get_account(session, acc_id) is None:
        raise AppError(
            code="account_not_found",
            message=f"Account {acc_id} does not exist.",
            status_code=404,
            details={"acc_id": acc_id},
        )
    rows, total = await transactions_repo.list_account_transactions(
        session, acc_id, direction=direction, ts_from=ts_from, ts_to=ts_to, limit=limit, offset=offset
    )
    return TransactionPage(
        items=[TransactionOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )
