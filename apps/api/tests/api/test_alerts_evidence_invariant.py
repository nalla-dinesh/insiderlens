"""Evidence invariant — EVERY alert from a full pipeline run, schema-validated.

Spec §5: loop over ALL alerts of the run; each must carry reasons>0 and evidence
with graph+timeline+thresholds keys. Also: alert is IMPOSSIBLE without them
(DB-level CHECK, proven in tests/test_alerts_constraints.py).
"""

from app.db.session import build_session_factory
from app.schemas.alerts import AlertDetail
from app.services.ingestion import IngestionService
from tests.conftest import needs_pg

pytestmark = needs_pg

ALL_BANDS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


async def test_every_alert_carries_full_evidence(client, engine, crafted_bundle):
    factory = build_session_factory(engine)
    await IngestionService(factory, crafted_bundle).run()
    assert (await client.post("/api/analysis/run")).status_code == 200

    page = (await client.get("/api/alerts", params={"limit": 500})).json()
    assert page["total"] >= 1

    for item in page["items"]:
        det = await client.get(f"/api/alerts/{item['alert_id']}")
        assert det.status_code == 200
        d = AlertDetail.model_validate(det.json())  # schema round-trip
        assert d.band in ALL_BANDS
        assert len(d.reasons) > 0
        assert d.score == sum(r.pts for r in d.reasons)
        ev = d.evidence
        for key in ("graph", "timeline", "thresholds", "records"):
            assert key in ev, f"alert {d.alert_id}: missing evidence.{key}"
        assert ev["graph"]["nodes"], f"alert {d.alert_id}: empty graph.nodes"
        assert ev["timeline"], f"alert {d.alert_id}: empty timeline"
        assert ev["thresholds"], f"alert {d.alert_id}: empty thresholds"
        assert ev["records"]["txn_ids"] or ev["records"]["log_ids"]


async def test_histogram_breakdown_consistent(client, engine, crafted_bundle):
    factory = build_session_factory(engine)
    await IngestionService(factory, crafted_bundle).run()
    rep = (await client.post("/api/analysis/run")).json()
    total = sum(rep["alerts_by_band"].values())
    page = (await client.get("/api/alerts", params={"limit": 500})).json()
    assert page["total"] == total
    for band in ALL_BANDS:
        got = sum(1 for i in page["items"] if i["band"] == band)
        assert got == rep["alerts_by_band"][band], f"band {band} count mismatch"
