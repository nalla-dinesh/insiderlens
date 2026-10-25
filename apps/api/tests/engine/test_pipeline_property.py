"""Pipeline-level invariants on the REAL seeded bundle (when reachable).

These are the Phase-04 DoD box-ticks — they read live engine output FOR REAL,
they do not stub. When the seeded DB is unreachable they skip loudly.

  1. Every persisted alert: score == sum(reasons.pts)           (iron law)
  2. Every persisted alert: non-empty evidence with records     (evidence law)
  3. S5 showcase: an alert containing employee 1017 is CRITICAL with
     rule_set ⊇ {E1, E2, E4, T1, F1} and score ∈ [130, 170]
  4. T5 must NOT fire on S5's account (the S5 ring is ACTIVE, dormancy off-limits)
"""

from tests.conftest import needs_pg  # shared `seeded_engine` fixture lives in tests/conftest.py

pytestmark = needs_pg


async def _run_pipeline(engine):
    from app.db.session import build_session_factory
    from app.services.pipeline import run_analysis
    from app.services.rules_config import get_rules_config
    from tests.conftest import RULES_YAML

    cfg = get_rules_config(str(RULES_YAML))
    factory = build_session_factory(engine)
    async with factory() as session:
        report = await run_analysis(session, cfg, str(RULES_YAML))
        from sqlalchemy import select

        from app.models.alert import Alert

        alerts = (
            (await session.execute(select(Alert).where(Alert.run_id == report["run_id"]))).scalars().all()
        )
    return report, alerts


async def test_iron_law_on_all_alerts(seeded_engine):
    _, alerts = await _run_pipeline(seeded_engine)
    assert alerts, "pipeline produced ZERO alerts on the seeded bundle — impossible"
    for a in alerts:
        assert a.score == sum(r["pts"] for r in a.reasons), (
            f"alert {a.alert_id}: iron law broken ({a.score} vs reasons)"
        )


async def test_evidence_law_on_all_alerts(seeded_engine):
    _, alerts = await _run_pipeline(seeded_engine)
    for a in alerts:
        ev = a.evidence
        assert ev.get("records"), f"alert {a.alert_id}: no records block"
        assert ev["records"]["txn_ids"] or ev["records"]["log_ids"], f"alert {a.alert_id}: no receipts at all"
        assert ev.get("timeline"), f"alert {a.alert_id}: empty timeline"
        assert "graph" in ev and "nodes" in ev["graph"]


async def test_s5_showcase_critical(seeded_engine):
    _, alerts = await _run_pipeline(seeded_engine)
    s5 = [a for a in alerts if 1017 in list(a.entity_ids)]
    assert s5, "no alert involves employee 1017 — S5 story broken"
    best = max(s5, key=lambda a: a.score)
    assert best.band == "CRITICAL", f"S5 alert band={best.band} (score {best.score})"
    assert 130 <= best.score <= 170, f"S5 score {best.score} outside [130,170]"
    assert {"E1", "E2", "E4", "T1", "F1"} <= set(best.rule_set), best.rule_set


async def test_t5_never_fires_on_s5_ring_accounts(seeded_engine):
    _, alerts = await _run_pipeline(seeded_engine)
    s5_accs = {200071, 200072, 200073}
    for a in alerts:
        if s5_accs & set(a.entity_ids):
            assert "T5" not in a.rule_set, f"alert {a.alert_id}: T5 dormant fired on an ACTIVE S5 account"
