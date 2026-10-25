"""The evidence law, enforced at the DB level: an alert with EMPTY reasons or
EMPTY evidence must be impossible to persist (Postgres CHECK constraints).
sqlite could never prove this — which is why these tests require real Postgres."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.alert import Alert
from app.models.run import Run
from tests.conftest import needs_pg

pytestmark = needs_pg

RUN = {"started_at": datetime(2026, 10, 23, tzinfo=UTC), "status": "RUNNING", "config": {}}

GOOD = dict(
    rule_set=["T1"],
    entity_type="ACCOUNT",
    entity_ids=[200001],
    score=70,
    band="HIGH",
    reasons=[{"rule": "T1", "pts": 40, "text": "cycle, retention 81%"}],
    evidence={
        "graph": {"nodes": [], "edges": []},
        "timeline": [],
        "thresholds": {},
        "records": {"txn_ids": [1], "log_ids": []},
    },
)


async def _new_run(session) -> Run:
    run = Run(**RUN)
    session.add(run)
    await session.flush()
    return run


async def test_empty_reasons_rejected(session):
    run = await _new_run(session)
    session.add(Alert(run_id=run.run_id, **{**GOOD, "reasons": []}))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_empty_evidence_rejected(session):
    run = await _new_run(session)
    session.add(Alert(run_id=run.run_id, **{**GOOD, "evidence": {}}))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_valid_alert_persists(session):
    run = await _new_run(session)
    alert = Alert(run_id=run.run_id, **GOOD)
    session.add(alert)
    await session.commit()
    assert alert.alert_id >= 1 and alert.status == "OPEN" and alert.score == 70
