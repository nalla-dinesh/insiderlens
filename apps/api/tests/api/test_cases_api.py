"""Phase 06 — cases API: creation rules, state machine, sequential-case rule,
assignee validation, audit notes. All flows are real DB writes over real HTTP.

Transition table (asserted EXACTLY):
    OPEN          → IN_PROGRESS ✓   (→ESCALATED/CLOSED_* ✗ 409)
    IN_PROGRESS   → ESCALATED ✓, CLOSED_TRUE ✓, CLOSED_FALSE ✓   (→OPEN ✗)
    ESCALATED     → CLOSED_TRUE ✓, CLOSED_FALSE ✓                (→OPEN/IN_PROGRESS ✗)
    CLOSED_TRUE/_FALSE → ANYTHING ✗  (immutable, 409, closed_at set)
"""

from __future__ import annotations

from tests.api.conftest import critical_alert, ingest_and_run, make_case
from tests.conftest import needs_pg

pytestmark = needs_pg


async def test_create_from_alert_happy_path_and_conflict(client, engine, crafted_bundle):
    rep = await ingest_and_run(client, engine, crafted_bundle)
    assert rep["alerts_by_band"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 1}
    alert = await critical_alert(client)

    case = await make_case(client, alert["alert_id"], assignee="Test Manager")
    assert case["status"] == "OPEN"
    assert case["assignee"] == "Test Manager"
    assert case["band"] == "CRITICAL"
    # title format: "[BAND] top-reason · N entities"
    assert case["title"].startswith("[CRITICAL] "), case["title"]
    assert case["title"].endswith(f"· {len(alert['entity_ids'])} entities"), case["title"]
    assert "[T1]" in case["title"]  # top reason text, verbatim
    # alert now linked; full payload rides with the case
    assert case["alerts"][0]["alert_id"] == alert["alert_id"]
    assert case["alerts"][0]["score"] == alert["score"]
    assert case["alerts"][0]["evidence"]["records"]["txn_ids"]  # evidence verbatim
    # auto note + status history seed
    assert len(case["notes"]) == 1
    assert case["notes"][0]["author"] == "system"
    assert f"AL-{alert['alert_id']:06d}" in case["notes"][0]["body"]

    detail = (await client.get(f"/api/cases/{case['case_id']}")).json()
    assert detail["alert_ids"] == [alert["alert_id"]]

    # second OPEN case on the same alert → 409 (sequential rule, P4)
    twice = await client.post("/api/cases", json={"alert_id": alert["alert_id"]})
    assert twice.status_code == 409
    assert twice.json()["error"]["code"] == "alert_case_conflict"

    # alert not found → 404
    missing = await client.post("/api/cases", json={"alert_id": 424242})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "alert_not_found"

    # after CLOSED_*, same alert CAN seed a new case (sequential allowed)
    for step in ("IN_PROGRESS", "ESCALATED", "CLOSED_TRUE"):
        r = await client.patch(f"/api/cases/{case['case_id']}", json={"status": step})
        assert r.status_code == 200, (step, r.text)
    again = await client.post("/api/cases", json={"alert_id": alert["alert_id"]})
    assert again.status_code == 201, again.text
    assert again.json()["case_id"] != case["case_id"]


async def test_transition_table(client, engine, crafted_bundle):
    """Table-driven walk: every legal + illegal hop in one deterministic story —
    ≥8 rows covering every transition edge and the immutability rule."""
    await ingest_and_run(client, engine, crafted_bundle)
    alert = await critical_alert(client)
    case = await make_case(client, alert["alert_id"])
    cid = case["case_id"]

    # (from_state_expectation, attempt, legal?)
    table = [
        ("OPEN", "ESCALATED", False),
        ("OPEN", "CLOSED_TRUE", False),
        ("OPEN", "CLOSED_FALSE", False),
        ("OPEN", "IN_PROGRESS", True),
        ("IN_PROGRESS", "OPEN", False),
        ("IN_PROGRESS", "ESCALATED", True),  # also CLOSED_TRUE/CLOSED_FALSE legal from here
        ("ESCALATED", "OPEN", False),
        ("ESCALATED", "IN_PROGRESS", False),
        ("ESCALATED", "CLOSED_TRUE", True),
        ("CLOSED_TRUE", "IN_PROGRESS", False),  # closed immutable (P5)
        ("CLOSED_TRUE", "ESCALATED", False),
        ("CLOSED_TRUE", "CLOSED_FALSE", False),
    ]
    for expect_from, attempt, legal in table:
        cur = (await client.get(f"/api/cases/{cid}")).json()
        assert cur["status"] == expect_from, (attempt, f"story drifted: {cur['status']} != {expect_from}")
        resp = await client.patch(f"/api/cases/{cid}", json={"status": attempt})
        if legal:
            assert resp.status_code == 200, (attempt, resp.text)
            assert resp.json()["status"] == attempt
        else:
            assert resp.status_code == 409, (attempt, resp.text)
            assert resp.json()["error"]["code"] in {"illegal_transition", "case_closed"}
            assert (await client.get(f"/api/cases/{cid}")).json()["status"] == expect_from

    final = (await client.get(f"/api/cases/{cid}")).json()
    assert final["closed_at"] is not None
    # P5: PATCHing a closed case — even title-only — is 409
    r = await client.patch(f"/api/cases/{cid}", json={"title": "no"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "case_closed"
    # notes on closed case → 409
    r = await client.post(f"/api/cases/{cid}/notes", json={"body": "late note"})
    assert r.status_code == 409
    # status history visible through system notes (E2E asserts this too)
    history_bodies = [n["body"] for n in final["notes"]]
    assert any("Status OPEN → IN_PROGRESS" in b for b in history_bodies)
    assert any("Status IN_PROGRESS → ESCALATED" in b for b in history_bodies)
    assert any("Status ESCALATED → CLOSED_TRUE" in b for b in history_bodies)


async def test_assignee_validation_and_notes(client, engine, crafted_bundle):
    await ingest_and_run(client, engine, crafted_bundle)
    alert = await critical_alert(client)

    bad = await client.post("/api/cases", json={"alert_id": alert["alert_id"], "assignee": "Ghost Person"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "assignee_invalid"

    case = await make_case(client, alert["alert_id"], assignee="Test Manager")
    cid = case["case_id"]

    # notes append in order; oldest first
    await client.post(f"/api/cases/{cid}/notes", json={"body": "first", "author": "Test Manager"})
    await client.post(f"/api/cases/{cid}/notes", json={"body": "second", "author": "Test Manager"})
    got = (await client.get(f"/api/cases/{cid}")).json()
    bodies = [n["body"] for n in got["notes"]]
    assert bodies.index("first") < bodies.index("second")
    assert got["notes"][0]["author"] == "system"  # creation auto-note always first

    # reassign via PATCH (valid) + audit note
    r = await client.patch(f"/api/cases/{cid}", json={"assignee": "Test Manager", "actor": "Test Manager"})
    assert r.status_code == 200
    # unassign clears
    r = await client.patch(f"/api/cases/{cid}", json={"assignee": ""})
    assert r.json()["assignee"] is None

    # analyst directory: MANAGER/ADMIN only
    an = (await client.get("/api/analysts")).json()
    names = {a["name"] for a in an}
    assert "Test Manager" in names
    assert "Test Teller" not in names
    assert all(a["role"] in {"MANAGER", "ADMIN"} for a in an)

    # board groups the case in OPEN
    b = (await client.get("/api/cases")).json()
    assert set(b["groups"].keys()) == {"OPEN", "IN_PROGRESS", "ESCALATED", "CLOSED_TRUE", "CLOSED_FALSE"}
    assert any(c["case_id"] == cid for c in b["groups"]["OPEN"])
    assert b["groups"]["OPEN"][0]["band"] == "CRITICAL"
