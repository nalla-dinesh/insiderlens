"""Read-only activity-log queries (employee actions). v1 feeds Phase 04 evidence
timelines; exposed here so Phase 03/04 add no new SQL modules."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog


async def list_logs_for_account(session: AsyncSession, acc_id: int, *, limit: int = 500) -> list[ActivityLog]:
    rows = (
        (
            await session.execute(
                select(ActivityLog)
                .where(ActivityLog.target_acc == acc_id)
                .order_by(ActivityLog.ts)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_logs_for_employee(
    session: AsyncSession,
    emp_id: int,
    *,
    ts_from: datetime | None = None,
    ts_to: datetime | None = None,
    limit: int = 1000,
) -> list[ActivityLog]:
    conds = [ActivityLog.emp_id == emp_id]
    if ts_from is not None:
        conds.append(ActivityLog.ts >= ts_from)
    if ts_to is not None:
        conds.append(ActivityLog.ts <= ts_to)
    rows = (
        (await session.execute(select(ActivityLog).where(*conds).order_by(ActivityLog.ts).limit(limit)))
        .scalars()
        .all()
    )
    return list(rows)
