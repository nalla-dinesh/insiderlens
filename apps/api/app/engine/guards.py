"""Legitimacy guards — the FALSE-POSITIVE DEFENSES, learned from the L1-L5 traps.

These are PART of the rules, not post-filters:
1. purpose exemption (salary/property/hospital/vendor flows never feed rule math),
2. T1 vetoes cycles containing >=2 exempt-purpose legs (kills vendor triangles),
3. T4 needs >=3 occurrences (one-off emergencies like L4 stay silent),
4. bands/multiples come ONLY from rules.yaml (T2/T3/T6).
"""

from __future__ import annotations

from app.engine.types import LegEvidence
from app.services.rules_config import RulesConfig


def exempt_purposes(cfg: RulesConfig) -> frozenset[str]:
    return frozenset(cfg.legitimacy_guards.exempt_purposes)


def is_exempt(purpose: str | None, cfg: RulesConfig) -> bool:
    return bool(purpose) and purpose in cfg.legitimacy_guards.exempt_purposes


def exempt_leg_count(legs: list[LegEvidence], cfg: RulesConfig) -> int:
    return sum(1 for leg in legs if is_exempt(leg.purpose, cfg))


def t2_bands_active(cfg: RulesConfig) -> list[tuple[float, float]]:
    """Configured sub-threshold watch bands (band 2 is optional)."""
    t2 = cfg.thresholds.t2_structuring
    bands = [(t2.band_lo, t2.band_hi)]
    if t2.band2_lo is not None and t2.band2_hi is not None:
        bands.append((t2.band2_lo, t2.band2_hi))
    return bands
