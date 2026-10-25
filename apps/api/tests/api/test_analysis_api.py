"""Phase-04 API: POST run -> alerts list/detail/patch (crafted S5-insider bundle).

Full-stack: real ingestion + real pipeline + real HTTP — the exact flow the
analyst UI drives. Numbers asserted match the by-hand derivation in
tests/api/conftest.py (ring 600k/585k/570k, actions at 22:13 IST, ...).
"""

import re

from app.db.session import build_session_factory
from app.services.ingestion import IngestionService
from tests.conftest import needs_pg

pytestmark = needs_pg

EXPECTED_RULES = {"T1", "E1", "E2", "E4", "F1", "F3"}
EXPECTED_SCORE = 150  # 40+10+20+15+25+10 base + 10+10+10 modifiers


async def _ingest_and_run(client, engine, bundle) -> dict:
    factory = build_session_factory(engine)
    await IngestionService(factory, bundle).run()
    resp = await client.post("/api/analysis/run")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _critical_alert(client) -> dict:
    page = (await client.get("/api/alerts", params={"band": "CRITICAL"})).json()
    assert page["total"] == 1, page
    return page["items"][0]


async def test_run_report_shape_and_hits(client, engine, crafted_bundle):
    rep = await _ingest_and_run(client, engine, crafted_bundle)
    assert rep["status"] == "COMPLETED", rep["errors"]
    assert rep["errors"] == []
    assert rep["alerts_by_band"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 1}
    assert rep["per_rule_hits"]["T1"] == 1
    assert rep["per_rule_hits"]["E1"] == 1
    assert rep["per_rule_hits"]["E2"] == 1
    assert rep["per_rule_hits"]["E4"] == 1
    assert rep["per_rule_hits"]["F1"] == 1
    assert rep["per_rule_hits"]["F3"] == 1
    assert rep["per_rule_hits"]["F2"] == 0  # no DISABLE_ALERT planted
    assert rep["duration_ms"] > 0


async def test_s5_style_critical_alert_exact_score(client, engine, crafted_bundle):
    await _ingest_and_run(client, engine, crafted_bundle)
    a = await _critical_alert(client)
    assert a["entity_ids"] == [1017, 200071, 200072, 200073]
    assert a["entity_type"] == "MIXED"
    assert set(a["rule_set"]) == EXPECTED_RULES
    assert a["score"] == EXPECTED_SCORE
    assert a["band"] == "CRITICAL"
    assert a["status"] == "OPEN"
    assert a["top_reasons"] and all(re.search(r"\d", t) for t in a["top_reasons"])
    # DoD: dormant reactivation must NOT pretend the active ring is dormant
    assert "T5" not in a["rule_set"]


async def test_alert_detail_iron_law_and_evidence(client, engine, crafted_bundle):
    await _ingest_and_run(client, engine, crafted_bundle)
    a = await _critical_alert(client)
    d = (await client.get(f"/api/alerts/{a['alert_id']}")).json()
    assert d["score"] == sum(r["pts"] for r in d["reasons"])  # iron law via API
    ev = d["evidence"]
    assert ev["graph"]["nodes"], "evidence graph must not be empty"
    assert ev["records"]["txn_ids"] == [601, 602, 603] or ev["records"]["log_ids"]
    assert ev["timeline"], "timeline must not be empty"
    # evidence thresholds reference rules.yaml — the explainability receipt
    assert any(gate["source"] == "rules.yaml" for gate in ev["thresholds"].values())


async def test_list_filters_band_status_rule(client, engine, crafted_bundle):
    await _ingest_and_run(client, engine, crafted_bundle)
    high = (await client.get("/api/alerts", params={"band": "HIGH"})).json()
    assert high["total"] == 0
    by_rule = (await client.get("/api/alerts", params={"rule": "F3"})).json()
    assert by_rule["total"] == 1
    assert "F3" in by_rule["items"][0]["rule_set"]
    none = (await client.get("/api/alerts", params={"rule": "T2"})).json()
    assert none["total"] == 0
    open_ = (await client.get("/api/alerts", params={"status": "OPEN"})).json()
    assert open_["total"] == 1


async def test_patch_status_roundtrip_and_guards(client, engine, crafted_bundle):
    await _ingest_and_run(client, engine, crafted_bundle)
    a = await _critical_alert(client)
    ok = await client.patch(f"/api/alerts/{a['alert_id']}/status", json={"status": "ACKNOWLEDGED"})
    assert ok.status_code == 200 and ok.json()["status"] == "ACKNOWLEDGED"
    again = (await client.get(f"/api/alerts/{a['alert_id']}")).json()
    assert again["status"] == "ACKNOWLEDGED"

    bad = await client.patch(f"/api/alerts/{a['alert_id']}/status", json={"status": "BOGUS"})
    assert bad.status_code == 422  # pydantic Literal gate

    missing = await client.get("/api/alerts/999999")
    assert missing.status_code == 404
    body = missing.json()
    assert body["error"]["code"] == "alert_not_found"  # our error-model envelope


async def test_timeline_endpoint_chronological(client, engine, crafted_bundle):
    await _ingest_and_run(client, engine, crafted_bundle)
    a = await _critical_alert(client)
    tl = (await client.get(f"/api/timeline/{a['alert_id']}")).json()["timeline"]
    assert len(tl) >= 4  # 3 legs + >=1 employee events
    kinds = {e["kind"] for e in tl}
    assert kinds == {"EMPLOYEE", "TXN"}
    ts_list = [e["ts"] for e in tl]
    assert ts_list == sorted(ts_list), "timeline must be chronological"
    # the night KYC edit precedes the ring's first leg in the merged story
    assert tl[0]["kind"] == "EMPLOYEE"


async def test_runs_endpoint_lists_completed(client, engine, crafted_bundle):
    await _ingest_and_run(client, engine, crafted_bundle)
    runs = (await client.get("/api/analysis/runs")).json()
    assert runs["total"] == 1
    r = runs["items"][0]
    assert r["status"] == "COMPLETED"
    assert r["alert_count"] == 1
    assert r["txn_count"] == 5
    assert r["finished_at"] is not None


async def test_dashboard_extensions_band_counts_amount_entity(client, engine, crafted_bundle):
    """Phase 05: AlertPage.band_counts, AlertSummary.max_amount, ?entity= filter."""
    await _ingest_and_run(client, engine, crafted_bundle)
    page = (await client.get("/api/alerts")).json()
    assert page["band_counts"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 1}
    item = page["items"][0]
    assert item["max_amount"] == 600000.0  # biggest cited ring leg
    assert item["entity_counts"] == {"accounts": 3, "employees": 1}  # 1017 + 3 ring accs
    # entity free-text filter: ring account 200072 exists on the CRITICAL alert
    hit = (await client.get("/api/alerts", params={"entity": 200072})).json()
    assert hit["total"] == 1 and 200072 in hit["items"][0]["entity_ids"]
    assert (await client.get("/api/alerts", params={"entity": 200080})).json()["total"] == 0
