"""Phase-07 evaluation tests — every metric asserted with exact counts.

Synthetic mini run built entirely inside the test (no external fixtures):
  - 7 suspicious scenarios (S1..S7) + 5 legit traps (L1..L5) planted as
    ground_truth rows with hand-picked entity ids.
  - Perfect detection run -> P=1, R=1, FPR=0, targets all pass.
  - One planted miss (S7 unalerted) -> R=6/7 -> recall target fails.
  - One trap alert (hits L4) -> FPR=0.2 -> targets.fpr_passed False.
  - Overlap-semantics: one entity shared by two scenarios counts for BOTH.
Isolation: conftest TRUNCATEs every table per test.
"""

import datetime as dt

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models.alert import Alert
from app.models.ground_truth import GroundTruth
from app.models.run import Run
from tests.conftest import needs_pg

pytestmark = needs_pg

_SHARED = False


async def _seed_gt(client: AsyncClient, *, shared_entity: bool = False) -> None:
    """One canonical GT universe: 7 S + 5 L rows."""
    susp = [[101], [102, 901], [103], [104], [105], [106], [107]]
    traps = [[201], [202], [203], [204], [205]]
    if shared_entity:
        susp[2] = [103, 901]  # entity 901 NOW belongs to S2 AND S3
    pool = client._transport.app.state.session_factory  # noqa: SLF001
    async with pool() as session:
        session.add_all(
            [
                GroundTruth(scenario_id=f"S{i + 1}", entity_type="ACCOUNT", entity_ids=e, is_suspicious=True)
                for i, e in enumerate(susp)
            ]
            + [
                GroundTruth(scenario_id=f"L{i + 1}", entity_type="ACCOUNT", entity_ids=e, is_suspicious=False)
                for i, e in enumerate(traps)
            ]
        )
        await session.commit()


async def _add_run(client: AsyncClient, alerts_to_entities: list[list[int]]) -> int:
    pool = client._transport.app.state.session_factory  # noqa: SLF001
    async with pool() as session:
        run = Run(started_at=dt.datetime.now(dt.UTC), status="COMPLETED", config={})
        session.add(run)
        await session.flush()
        run_id = int(run.run_id)
        for i, ents in enumerate(alerts_to_entities):
            session.add(
                Alert(
                    run_id=run_id,
                    rule_set=["T1"],
                    entity_type="ACCOUNT",
                    entity_ids=ents,
                    score=150,
                    band="CRITICAL",
                    reasons=[{"rule": "T1", "pts": 40, "text": f"synthetic hit {i}"}],
                    evidence={"graph": {"nodes": [], "edges": []}, "timeline": [], "thresholds": {}},
                    status="OPEN",
                )
            )
        await session.commit()
        return run_id


ALL_7 = [[101], [102], [103], [104], [105], [106], [107]]


async def test_perfect_run_metrics(client: AsyncClient, engine: AsyncEngine) -> None:
    await _seed_gt(client)
    run_id = await _add_run(client, ALL_7)
    r = await client.get(f"/api/evaluation/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"] == {"tp": 7, "fp": 0, "fn": 0, "tn": 5}
    assert body["precision"] == 1.0 and body["recall"] == 1.0 and body["fpr"] == 0.0
    assert body["f1"] == 1.0
    assert body["targets"]["passed"] is True
    assert body["alerts_on_tagged_suspicious"] == 7
    assert body["alerts_on_tagged_legit"] == 0
    assert body["alerts_unverified"] == 0
    srow = next(r for r in body["scenario_rows"] if r["scenario_id"] == "S1")
    assert srow["tag"] == "TP" and srow["hit"] is True and len(srow["matching_alert_ids"]) == 1


async def test_one_planted_miss_recall_6_of_7(client: AsyncClient, engine: AsyncEngine) -> None:
    await _seed_gt(client)
    run_id = await _add_run(client, ALL_7[:-1])  # 107 never alerted
    body = (await client.get(f"/api/evaluation/{run_id}")).json()
    assert body["counts"] == {"tp": 6, "fp": 0, "fn": 1, "tn": 5}
    assert body["recall"] == round(6 / 7, 4)
    assert body["targets"]["recall_passed"] is False  # 0.8571 < 0.90
    assert body["targets"]["passed"] is False
    s7 = next(r for r in body["scenario_rows"] if r["scenario_id"] == "S7")
    assert s7["tag"] == "FN" and s7["matching_alert_ids"] == []


async def test_trap_alert_fpr_and_targets_flag(client: AsyncClient, engine: AsyncEngine) -> None:
    await _seed_gt(client)
    run_id = await _add_run(client, [*ALL_7, [204]])  # alert touches trap L4
    body = (await client.get(f"/api/evaluation/{run_id}")).json()
    assert body["counts"] == {"tp": 7, "fp": 1, "fn": 0, "tn": 4}
    assert body["fpr"] == 0.2  # 1/5
    assert body["targets"]["fpr_passed"] is False
    assert body["targets"]["passed"] is False
    assert body["alerts_on_tagged_legit"] == 1
    l4 = next(r for r in body["scenario_rows"] if r["scenario_id"] == "L4")
    assert l4["tag"] == "FP" and len(l4["matching_alert_ids"]) == 1


async def test_alert_bucket_unverified_not_mixed(client: AsyncClient, engine: AsyncEngine) -> None:
    await _seed_gt(client)
    # one alert on totally unknown entities (P2: not FP — report separately)
    run_id = await _add_run(client, [[101], [999001, 999002]])
    body = (await client.get(f"/api/evaluation/{run_id}")).json()
    assert body["counts"]["fp"] == 0  # unknown-entity alert must NEVER inflate FP
    assert body["alerts_unverified"] == 1
    assert body["alert_count"] == 2


async def test_shared_entity_counts_for_both_scenarios(client: AsyncClient, engine: AsyncEngine) -> None:
    await _seed_gt(client, shared_entity=True)  # 901 now in S2 AND S3
    run_id = await _add_run(client, [[901]])
    body = (await client.get(f"/api/evaluation/{run_id}")).json()
    s2 = next(r for r in body["scenario_rows"] if r["scenario_id"] == "S2")
    s3 = next(r for r in body["scenario_rows"] if r["scenario_id"] == "S3")
    assert s2["hit"] and s3["hit"], "overlap semantics: shared entity counts for both scenarios"
    assert body["counts"]["tp"] == 2


async def test_compare_endpoint_and_404(client: AsyncClient, engine: AsyncEngine) -> None:
    await _seed_gt(client)
    run_a = await _add_run(client, ALL_7)
    run_b = await _add_run(client, ALL_7[:3])
    cmp_r = await client.get(f"/api/evaluation/compare?run_a={run_a}&run_b={run_b}")
    assert cmp_r.status_code == 200
    j = cmp_r.json()
    assert j["run_a"]["recall"] == 1.0 and j["run_b"]["recall"] == round(3 / 7, 4)
    assert j["deltas"]["recall"] == round(round(3 / 7, 4) - 1.0, 4)

    same = await client.get(f"/api/evaluation/compare?run_a={run_a}&run_b={run_a}")
    assert same.status_code == 422
    assert same.json()["error"]["code"] == "same_run_compare"

    missing = await client.get("/api/evaluation/999999999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "run_not_found"
