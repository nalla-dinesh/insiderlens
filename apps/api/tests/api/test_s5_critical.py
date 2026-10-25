"""S5 showcase (spec §5): the insider ring alert on the REAL seeded bundle.

- an alert containing employee 1017 must be CRITICAL
- score in [130, 170]
- rule_set ⊇ {E1, E2, E4, T1, F1}
- T5 (dormant reactivation) must NEVER appear on the ACTIVE S5 ring accounts
"""

from tests.conftest import needs_pg

pytestmark = needs_pg

S5_EMP = 1017
S5_RING_ACCS = {200071, 200072, 200073}
S5_REQUIRED = {"E1", "E2", "E4", "T1", "F1"}


async def _fresh_real_run(seeded_engine):
    """Run the FULL pipeline against the seeded bundle, reading alerts back."""
    from sqlalchemy import select

    from app.db.session import build_session_factory
    from app.models.alert import Alert
    from app.services.pipeline import run_analysis
    from app.services.rules_config import get_rules_config
    from tests.conftest import RULES_YAML

    cfg = get_rules_config(str(RULES_YAML))
    factory = build_session_factory(seeded_engine)
    async with factory() as session:
        rep = await run_analysis(session, cfg, str(RULES_YAML))
        alerts = (
            (
                await session.execute(
                    select(Alert)
                    .where(Alert.run_id == rep["run_id"])  # THIS run only —
                    .order_by(Alert.score.desc())
                )
            )
            .scalars()
            .all()
        )  # older runs' alerts stay history
    return alerts


async def test_s5_insider_ring_is_critical(seeded_engine):
    alerts = await _fresh_real_run(seeded_engine)
    s5 = [a for a in alerts if S5_EMP in list(a.entity_ids)]
    assert s5, "no alert contains employee 1017 — S5 detection is broken"
    best = s5[0]
    assert best.band == "CRITICAL", f"S5 alert band={best.band}, score={best.score}"
    assert 130 <= best.score <= 170, f"S5 score {best.score} outside [130, 170]"
    assert S5_REQUIRED <= set(best.rule_set), (
        f"S5 rule_set {best.rule_set} missing {S5_REQUIRED - set(best.rule_set)}"
    )
    residual = [a for a in s5[1:] if a.band == "CRITICAL"]
    assert not residual, "exactly ONE CRITICAL alert should carry the S5 story"


async def test_t5_dormant_never_fires_on_active_ring(seeded_engine):
    alerts = await _fresh_real_run(seeded_engine)
    for a in alerts:
        if S5_RING_ACCS & set(a.entity_ids):
            assert "T5" not in a.rule_set, f"alert {a.alert_id}: T5 over-matched the ACTIVE ring accounts"
