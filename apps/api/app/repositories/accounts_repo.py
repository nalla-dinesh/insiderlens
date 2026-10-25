"""Read-only account queries for v0 endpoints."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account


async def get_account(session: AsyncSession, acc_id: int) -> Account | None:
    return await session.get(Account, acc_id)


async def list_accounts(session: AsyncSession, limit: int, offset: int) -> tuple[list[Account], int]:
    total = (await session.execute(select(func.count(Account.acc_id)))).scalar_one()
    rows = (
        (await session.execute(select(Account).order_by(Account.acc_id).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return list(rows), int(total)
