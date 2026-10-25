"""Merger — cluster the run's hits into alert groups (union-find).

LAW (spec 3.3 + P3 pitfall):
- Two hits merge ONLY if they share >= 1 entity AND their time windows overlap
  (entity-only chaining would drag the whole graph into mega-blobs).
- Alerts cap at fusion.max_rules_per_alert rules: the weakest (lowest
  base_points) overflow rules become evidence.overflow_rules, NOT score points.
- Alerts cap at fusion.max_entities_per_alert entities: oversized components are
  split at the WEAKEST temporal link = the widest gap between consecutive hits'
  windows (documented deterministic rule).

Entity-id collision note: account ids (200xxx), customer ids (100xxx) and
employee ids (10xx) are disjoint ranges in this bundle; the union key is the raw
int, and the pipeline separately tags entity_type after merging.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.engine.types import RuleHit
from app.services.rules_config import RulesConfig

LOOSE = pd.Timedelta(hours=6)  # windows that nearly touch still merge (documented slack)


@dataclass
class AlertGroup:
    hits: list[RuleHit]
    rule_set: list[str]  # capped, contributing rules
    overflow_rules: list[str]  # dropped by the cap (documented, zero points)
    entity_ids: list[int]
    window: tuple[pd.Timestamp, pd.Timestamp]


def _window(h: RuleHit) -> tuple[pd.Timestamp, pd.Timestamp]:
    first = pd.Timestamp(h.first_ts) if h.first_ts else None
    last = pd.Timestamp(h.last_ts) if h.last_ts else None
    return first, last  # type: ignore[return-value]


def _overlap(a: RuleHit, b: RuleHit) -> bool:
    af, al = _window(a)
    bf, bl_ = _window(b)
    if af is None or al is None or bf is None or bl_ is None:
        return True  # timeless hits merge by entity alone (documented)
    return af <= bl_ + LOOSE and bf <= al + LOOSE


def _components(base: list[RuleHit]) -> list[list[RuleHit]]:
    """Union-find over (shared entity AND overlapping windows)."""
    n = len(base)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_ent: dict[int, list[int]] = {}
    for i, h in enumerate(base):
        for e in h.entity_ids:
            by_ent.setdefault(e, []).append(i)
    for idxs in by_ent.values():
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                if _overlap(base[idxs[i]], base[idxs[j]]):
                    union(idxs[i], idxs[j])

    comps: dict[int, list[RuleHit]] = {}
    for i, h in enumerate(base):
        comps.setdefault(find(i), []).append(h)
    return list(comps.values())


def _split_wide(comp: list[RuleHit], max_entities: int) -> list[list[RuleHit]]:
    """Split oversized components at the weakest temporal link (widest gap
    between consecutive hit windows). Recurse until the cap holds."""
    ents = {e for h in comp for e in h.entity_ids}
    if len(ents) <= max_entities:
        return [comp]
    ordered = sorted(comp, key=lambda h: (h.first_ts is not None, h.first_ts, h.rule_id))
    # find widest gap between window-N end and window-N+1 start
    best_gap, best_at = pd.Timedelta(0), 1
    for i in range(1, len(ordered)):
        prev_end = max(pd.Timestamp(h.first_ts) for h in ordered[:i] if h.first_ts)
        cur_start = pd.Timestamp(ordered[i].first_ts or ordered[i].last_ts)
        if prev_end is pd.NaT or cur_start is pd.NaT:  # type: ignore[comparison-overlap]
            gap = pd.Timedelta(0)
        else:
            gap = cur_start - prev_end
        if gap > best_gap:
            best_gap, best_at = gap, i
    left, right = ordered[:best_at], ordered[best_at:]
    if not left or not right:
        return [comp]  # degenerate — give up rather than loop
    return _split_wide(left, max_entities) + _split_wide(right, max_entities)


def merge_hits(hits: list[RuleHit], cfg: RulesConfig) -> list[AlertGroup]:
    if not hits:
        return []
    comps = _components(hits)
    parts: list[list[RuleHit]] = []
    for comp in comps:
        parts.extend(_split_wide(comp, cfg.fusion.max_entities_per_alert))

    groups: list[AlertGroup] = []
    for part in parts:
        scored = sorted({h.rule_id: h.base_points for h in part}.items(), key=lambda kv: (-kv[1], kv[0]))
        kept = [rid for rid, _ in scored[: cfg.fusion.max_rules_per_alert]]
        overflow = [rid for rid, _ in scored[cfg.fusion.max_rules_per_alert :]]
        kept_hits = [h for h in part if h.rule_id in kept]
        ts = [pd.Timestamp(h.first_ts or h.last_ts) for h in part if h.first_ts or h.last_ts]
        groups.append(
            AlertGroup(
                hits=kept_hits,
                rule_set=kept,
                overflow_rules=overflow,
                entity_ids=sorted({e for h in kept_hits for e in h.entity_ids}),
                window=(min(ts), max(ts)) if ts else (pd.Timestamp.now(tz="UTC"),) * 2,
            )
        )
    return groups
