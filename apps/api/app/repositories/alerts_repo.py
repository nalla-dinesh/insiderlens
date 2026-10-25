"""Alerts repository — list filter query + detail fetch.

Phase-05 extensions (minimal, prompted by dashboard needs):
- `band_counts`: header cards show per-band totals UNDER the current rule/status/
  entity filters (band filter itself excluded — you still see the distribution).
- `max_amount`: the largest txn leg cited in each alert's evidence — the Amount
  column. Batched: ONE txn fetch for the whole page, max-mapped in Python.
- `entity` filter: analyst free-texts an account/employee id into the filter bar.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.alert import Alert
from app.models.employee import Employee
from app.models.run import Run
from app.models.transaction import Transaction

BANDS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _list_filters(q, band: str | None, status: str | None, rule: str | None, entity: int | None):
    if band:
        q = q.where(Alert.band == band.upper())
    if status:
        q = q.where(Alert.status == status.upper())
    if rule:
        q = q.where(Alert.rule_set.contains([rule.upper()]))
    if entity is not None:
        q = q.where(Alert.entity_ids.contains([entity]))
    return q


async def list_alerts(
    session: AsyncSession,
    band: str | None,
    status: str | None,
    rule: str | None,
    limit: int,
    offset: int,
    entity: int | None = None,
) -> tuple[list[Alert], int, dict[str, int], dict[int, float], dict[int, dict[str, int]]]:
    count_q = select(func.count()).select_from(Alert)
    total = int((await session.execute(_list_filters(count_q, band, status, rule, entity))).scalar_one())

    # per-band distribution obeying every filter EXCEPT the band chip itself
    band_q = select(Alert.band, func.count()).group_by(Alert.band)
    band_q = _list_filters(band_q, None, status, rule, entity)
    band_counts = {b: 0 for b in BANDS}
    for b, c in (await session.execute(band_q)).all():
        band_counts[str(b)] = int(c)

    page_q = select(Alert)
    page_q = _list_filters(page_q, band, status, rule, entity)
    rows = list(
        (
            await session.execute(
                page_q.order_by(Alert.score.desc(), Alert.alert_id).limit(limit).offset(offset),
            )
        )
        .scalars()
        .all()
    )

    # max cited txn amount per alert — ONE batched txn query for the whole page
    by_alert: dict[int, list[int]] = {}
    all_ids: list[int] = []
    for a in rows:
        ids = [int(t) for t in a.evidence.get("records", {}).get("txn_ids", [])]
        by_alert[int(a.alert_id)] = ids
        all_ids.extend(ids)
    max_amounts: dict[int, float] = {}
    if all_ids:
        amt_rows = (
            await session.execute(
                select(Transaction.txn_id, Transaction.amount).where(
                    Transaction.txn_id.in_(sorted(set(all_ids)))
                ),
            )
        ).all()
        amounts = {int(t): float(v) for t, v in amt_rows}
        for aid, ids in by_alert.items():
            vals = [amounts[i] for i in ids if i in amounts]
            if vals:
                max_amounts[aid] = max(vals)

    # entity kind counts per alert — id ranges collide between customers and
    # accounts, so ask the two source tables (batched for the page)
    page_entities = sorted({e for a in rows for e in a.entity_ids})
    acc_set: set[int] = set()
    emp_set: set[int] = set()
    if page_entities:
        acc_set = {
            int(v)
            for v in (await session.execute(select(Account.acc_id).where(Account.acc_id.in_(page_entities))))
            .scalars()
            .all()
        }
        emp_set = {
            int(v)
            for v in (
                await session.execute(select(Employee.emp_id).where(Employee.emp_id.in_(page_entities)))
            )
            .scalars()
            .all()
        }
    entity_counts: dict[int, dict[str, int]] = {}
    for a in rows:
        ids = [int(e) for e in a.entity_ids]
        entity_counts[int(a.alert_id)] = {
            "accounts": sum(1 for e in ids if e in acc_set),
            "employees": sum(1 for e in ids if e in emp_set),
        }
    return rows, total, band_counts, max_amounts, entity_counts


async def get_alert(session: AsyncSession, alert_id: int) -> Alert | None:
    return (await session.execute(select(Alert).where(Alert.alert_id == alert_id))).scalar_one_or_none()


async def list_runs(session: AsyncSession, limit: int, offset: int) -> tuple[Sequence[Run], int]:
    total = int((await session.execute(select(func.count()).select_from(Run))).scalar_one())
    rows = (
        (await session.execute(select(Run).order_by(Run.run_id.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return list(rows), total
