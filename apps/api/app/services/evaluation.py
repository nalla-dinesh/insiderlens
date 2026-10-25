"""EvaluationService — Phase 07. The ONLY detection-adjacent module permitted to
read ground_truth (ingestion merely bulk-loads the CSV; the engine NEVER does —
guarded by an AST test).

Law (spec):
- Scenario-level classification, one *run* at a time.
- For each suspicious s: TP if >=1 alert of the run overlaps ANY of its tagged
  entity ids; else FN. For each legit trap l: FP if an overlap exists, else TN.
- Unverified alerts (zero overlap with ANY ground-truth entity) are reported
  separately — they are neither TP nor FP (P2: mixing them inflates FPR).
- Overlap evaluated IN SQL with Postgres `&&` (P1: never hydrate 40k alerts).

Cache is per-(process, run_id) — keyed invalidation, never global (P3).
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.ground_truth import GroundTruth
from app.models.run import Run
from app.schemas.evaluation import (
    CompareReport,
    EvaluationReport,
    MetricCounts,
    ScenarioRow,
    Targets,
)

RECALL_GOAL = 0.90
PRECISION_GOAL = 0.85
FPR_GOAL = 0.05


@dataclass
class _ScenarioJoin:
    """ONE verdict per scenario_id — never per GT bookkeeping row.
    Ground truth stores one row per (scenario, entity); S3 alone has 16 rows.
    The metric universe is 7 suspicious + 5 traps, so rows are collapsed by
    scenario_id (entity universe = union, matches = union of run's alerts)."""

    scenario_id: str
    is_suspicious: bool
    entity_ids: set[int]
    matching: dict[int, str]  # alert_id -> top_reason


class EvaluationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def classify_scenarios(self, run_id: int) -> list[_ScenarioJoin]:
        """SQL overlap per GT row (alerts.entity_ids && row.entity_ids — P1),
        then collapse to one verdict per scenario (order: eerste gt_id)."""
        gt = (await self.session.execute(select(GroundTruth).order_by(GroundTruth.gt_id))).scalars().all()

        collapsed: dict[str, _ScenarioJoin] = {}
        for g in gt:
            stmt = (
                select(Alert.alert_id, Alert.reasons)
                .where(Alert.run_id == run_id, Alert.entity_ids.overlap(g.entity_ids))
                .order_by(Alert.alert_id)
            )
            hits = (await self.session.execute(stmt)).all()
            join = collapsed.get(g.scenario_id)
            if join is None:
                join = _ScenarioJoin(
                    scenario_id=g.scenario_id,
                    is_suspicious=bool(g.is_suspicious),
                    entity_ids=set(),
                    matching={},
                )
                collapsed[g.scenario_id] = join
            join.entity_ids.update(int(e) for e in g.entity_ids)
            for aid, reasons in hits:
                join.matching.setdefault(int(aid), reasons[0]["text"] if reasons else "")
        return list(collapsed.values())

    @staticmethod
    def _classify(row: _ScenarioJoin) -> str:
        if row.is_suspicious:
            return "TP" if row.matching else "FN"
        return "FP" if row.matching else "TN"

    @staticmethod
    def compute_metrics(rows: list[_ScenarioJoin]) -> MetricCounts:
        c = MetricCounts(tp=0, fp=0, fn=0, tn=0)
        for row in rows:
            tag = EvaluationService._classify(row)
            setattr(c, tag.lower(), getattr(c, tag.lower()) + 1)
        return c

    async def _alert_bucket_counts(
        self, run_id: int, scenario_rows: list[_ScenarioJoin]
    ) -> tuple[int, int, int, int]:
        """(total, on_suspicious, on_legit, unverified) for the run's alerts.
        Overlap again in SQL against the tagged entity universe per side."""
        total = int(
            (
                await self.session.execute(select(func.count(Alert.alert_id)).where(Alert.run_id == run_id))
            ).scalar_one()
        )

        def _tagged_ids(susp: bool) -> list[int]:
            return sorted(int(e) for r in scenario_rows if r.is_suspicious == susp for e in r.entity_ids)

        async def _overlapping(ids: list[int]) -> int:
            if not ids:
                return 0
            stmt = select(func.count(Alert.alert_id)).where(
                Alert.run_id == run_id, Alert.entity_ids.overlap(ids)
            )
            return int((await self.session.execute(stmt)).scalar_one())

        on_susp = await _overlapping(_tagged_ids(True))
        on_trap = await _overlapping(_tagged_ids(False))
        return total, on_susp, on_trap, max(total - on_susp - on_trap, 0)

    async def evaluate(self, run_id: int) -> EvaluationReport:
        run = (await self.session.execute(select(Run).where(Run.run_id == run_id))).scalar_one_or_none()
        if run is None:
            from app.core.errors import AppError

            raise AppError(code="run_not_found", message=f"run {run_id} does not exist.", status_code=404)

        joins = await self.classify_scenarios(run_id)
        c = self.compute_metrics(joins)

        precision = c.tp / (c.tp + c.fp) if (c.tp + c.fp) else 1.0
        recall = c.tp / (c.tp + c.fn) if (c.tp + c.fn) else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        fpr = c.fp / (c.fp + c.tn) if (c.fp + c.tn) else 0.0

        r_ok, p_ok, fpr_ok = recall >= RECALL_GOAL, precision >= PRECISION_GOAL, fpr <= FPR_GOAL

        total, on_susp, on_trap, unverified = await self._alert_bucket_counts(run_id, joins)

        rows_out: list[_ScenarioJoin] = sorted(joins, key=lambda r: r.is_suspicious)
        return EvaluationReport(
            run_id=run_id,
            alert_count=total,
            counts=c,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            fpr=round(fpr, 4),
            targets=Targets(
                recall_passed=r_ok, precision_passed=p_ok, fpr_passed=fpr_ok, passed=r_ok and p_ok and fpr_ok
            ),
            alerts_on_tagged_suspicious=on_susp,
            alerts_on_tagged_legit=on_trap,
            alerts_unverified=unverified,
            scenario_rows=[
                ScenarioRow(
                    scenario_id=r.scenario_id,
                    is_suspicious=r.is_suspicious,
                    hit=bool(r.matching),
                    tag=self._classify(r),
                    entity_ids=sorted(r.entity_ids),
                    matching_alert_ids=sorted(r.matching),
                    note=(next(iter(r.matching.values())) if r.matching else ""),
                )
                for r in rows_out
            ],
        )

    async def compare(self, run_a: int, run_b: int) -> CompareReport:
        a, b = await self.evaluate(run_a), await self.evaluate(run_b)
        delta_metrics = ("precision", "recall", "f1", "fpr")
        deltas = {m: round(getattr(b, m) - getattr(a, m), 4) for m in delta_metrics}
        return CompareReport(run_a=a, run_b=b, deltas=deltas)


_cache: dict[int, EvaluationReport] = {}


async def evaluate_cached(session: AsyncSession, run_id: int) -> EvaluationReport:
    """Per-(process, run_id) in-memory cache (P3 — never global, and a run's
    verdicts are immutable once COMPLETED)."""
    if run_id in _cache:
        return _cache[run_id]
    report = await EvaluationService(session).evaluate(run_id)
    _cache[run_id] = report
    return report
