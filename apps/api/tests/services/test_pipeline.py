"""Pipeline service (mini benign bundle): run bookkeeping + alert-vs-signal policy.

The conftest MINI bundle is deliberately LOW-signal:
  - 1002 (TELLER) KYC_EDIT -> E2+E4 solo corroboration (2 rules) -> LOW alert
  - 1003 (ADMIN) night LOGIN -> login is NOT sensitive, so nothing
  - 1001 KYC_EDIT 17:45 UTC = 23:15 IST -> E1+E4 pair -> LOW alert
Everything scoring under MEDIUM with >=2 distinct rules still persists; truly
solo blips drop to 'signals' (run stats only).
"""

from app.db.session import build_session_factory
from app.services.ingestion import IngestionService
from app.services.pipeline import run_analysis
from app.services.rules_config import get_rules_config
from tests.conftest import RULES_YAML, needs_pg

pytestmark = needs_pg


async def _setup(engine, bundle):
    factory = build_session_factory(engine)
    await IngestionService(factory, bundle).run()
    cfg = get_rules_config(str(RULES_YAML))
    async with factory() as session:
        rep = await run_analysis(session, cfg, str(RULES_YAML))
    return factory, rep


async def test_run_row_bookkeeping_and_iron_law(engine, mini_bundle):
    factory, rep = await _setup(engine, mini_bundle)
    assert rep["status"] == "COMPLETED", rep["errors"]
    assert rep["duration_ms"] > 0

    from sqlalchemy import func, select

    from app.models.alert import Alert
    from app.models.run import Run

    async with factory() as s:
        run = (await s.execute(select(Run).where(Run.run_id == rep["run_id"]))).scalar_one()
        assert run.status == "COMPLETED"
        assert run.txn_count == 5
        alerts = (await s.execute(select(Alert))).scalars().all()
        assert len(alerts) == run.alert_count

        for a in alerts:
            assert a.score == sum(r["pts"] for r in a.reasons)  # iron law
            assert a.evidence["records"]["txn_ids"] or a.evidence["records"]["log_ids"]
            assert a.evidence["timeline"]

        # every band in the histogram equals persisted row counts
        bands = dict((await s.execute(select(Alert.band, func.count()).group_by(Alert.band))).all())
        for b, c in bands.items():
            assert rep["alerts_by_band"][b] == c


async def test_solo_low_e4_is_signal_not_alert(engine, tmp_path):
    """Exactly one night-time config change by an officer (allowed by role!):
    E1+E4 merge => 2 rules -> persists as LOW. Single E4-like LOW cases drop.
    Here we craft ONE DISABLE_ALERT by an ADMIN at noon: it is high-risk (E4),
    allowed for ADMIN (no E2), daytime (no E1) => SOLO LOW -> signal."""
    import hashlib
    import json

    from tests.conftest import MINI

    data = dict(MINI)
    data["activity_log"] = (
        "log_id,emp_id,ts,action,target_acc,details,ip,device,off_hours,role_violation\n"
        "1,1003,2026-07-05T06:30:00Z,DISABLE_ALERT,200004,{},10.20.3.2,branch-terminal,False,False\n"
    )
    data["ground_truth"] = "gt_id,scenario_id,entity_type,entity_ids,is_suspicious\n"
    d = tmp_path / "generated"
    d.mkdir()
    files = {}
    for name, content in data.items():
        p = d / f"{name}.csv"
        p.write_text(content, encoding="utf-8", newline="")
        files[name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    (d / "meta.json").write_text(json.dumps({"files": files}), encoding="utf-8", newline="")

    factory, rep = await _setup(engine, d)
    assert rep["per_rule_hits"]["E4"] == 1
    assert rep["signals_dropped"] >= 1, "solo low-signal E4 must NOT open an alert"
    from sqlalchemy import select

    from app.models.alert import Alert

    async with factory() as s:
        alerts = (await s.execute(select(Alert))).scalars().all()
    assert alerts == [] or all(1003 not in a.entity_ids for a in alerts)
