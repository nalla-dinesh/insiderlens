"""Schemas for the Phase-07 evaluation harness.

Law (spec §2): scenario-level classification against ground_truth — never mixed
silently with alert-level trivia; every ratio keeps its raw counts beside it
("6/7"), because 7 suspicious + 5 trap denominators are small.
"""

from pydantic import BaseModel, Field


class ScenarioRow(BaseModel):
    """One line of the S1-S7 / L1-L5 evidence table."""

    scenario_id: str
    is_suspicious: bool
    hit: bool  # suspicious: >=1 alert overlaps => TP row; trap: >=1 alert overlaps => FP row
    tag: str  # TP / FN / FP / TN (classification of THIS scenario for THIS run)
    entity_ids: list[int]
    matching_alert_ids: list[int] = Field(default_factory=list)
    note: str = ""  # one-liner from the top matching alert's first reason (verbatim evidence)


class MetricCounts(BaseModel):
    tp: int
    fp: int
    fn: int
    tn: int


class Targets(BaseModel):
    recall_goal: float = 0.90
    precision_goal: float = 0.85
    fpr_goal: float = 0.05
    recall_passed: bool
    precision_passed: bool
    fpr_passed: bool
    passed: bool


class EvaluationReport(BaseModel):
    run_id: int
    alert_count: int
    counts: MetricCounts
    precision: float
    recall: float
    f1: float
    fpr: float
    targets: Targets
    # honest context (P2): alerts on entities with NO ground-truth tag are
    # reported UNVERIFIED — they are not counted as FP and not as TP.
    alerts_on_tagged_suspicious: int
    alerts_on_tagged_legit: int
    alerts_unverified: int
    scenario_rows: list[ScenarioRow]


class CompareReport(BaseModel):
    run_a: EvaluationReport
    run_b: EvaluationReport
    deltas: dict[str, float]  # metric -> (run_b - run_a); + for recall is good, + for fpr is bad
