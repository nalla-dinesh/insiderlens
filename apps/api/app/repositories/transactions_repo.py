"""Read-only transaction queries for v0 endpoints."""

from datetime import datetime
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction

Direction = Literal["in", "out", "both"]


async def list_account_transactions(
    session: AsyncSession,
    acc_id: int,
    *,
    direction: Direction = "both",
    ts_from: datetime | None = None,
    ts_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    if direction == "in":
        scope = Transaction.to_acc == acc_id
    elif direction == "out":
        scope = Transaction.from_acc == acc_id
    else:
        scope = or_(Transaction.from_acc == acc_id, Transaction.to_acc == acc_id)

    conds = [scope]
    if ts_from is not None:
        conds.append(Transaction.ts >= ts_from)
    if ts_to is not None:
        conds.append(Transaction.ts <= ts_to)

    total = (await session.execute(select(func.count(Transaction.txn_id)).where(*conds))).scalar_one()
    rows = (
        (
            await session.execute(
                select(Transaction).where(*conds).order_by(Transaction.ts).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)
