"""rules.yaml -> typed RulesConfig. Fail-fast law: a missing/typo'd key crashes
startup naming the exact key — the engine must never fall back to magic numbers.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class RulesConfigError(RuntimeError):
    """Raised when infra/config/rules.yaml is missing or invalid. Message names the key."""


class CircularCfg(BaseModel):
    window_days: int = Field(gt=0)
    min_retention: float = Field(gt=0, le=1)
    min_len: int = Field(ge=3)
    max_len: int = Field(ge=3)
    min_leg_amount: float | None = None  # Phase 03: prune noise legs below this


class StructuringCfg(BaseModel):
    band_lo: float
    band_hi: float
    band2_lo: float | None = None  # optional second watch band
    band2_hi: float | None = None
    min_count: int = Field(ge=2)
    window_days: int = Field(gt=0)


class FanInCfg(BaseModel):
    min_in_degree: int = Field(ge=2)
    window_days: int = Field(gt=0)
    leg_min_amount: float | None = None  # Phase 03: inbound leg floor (smurf chunks)
    sub_threshold_fraction: float = Field(gt=0, le=1)
    bulk_out_multiple: float = Field(gt=1)
    bulk_window_hours: int = Field(gt=0)


class PassthroughCfg(BaseModel):
    forward_ratio: float = Field(gt=0, le=1)
    window_hours: int = Field(gt=0)
    min_occurrences: int = Field(ge=2)
    max_kept_fraction: float = Field(gt=0, le=1)
    max_fraction_std: float = 0.1  # corridor discipline gate
    min_route_share: float = 0.5  # next-hop concentration gate


class DormantCfg(BaseModel):
    dormant_days: int = Field(gt=0)
    burst_amount: float = Field(gt=0)
    burst_window_hours: int = Field(gt=0)
    window_silence_days: int = 30  # window-snapshot path (see rules.yaml comment)


class ProfileCfg(BaseModel):
    multiple: float = Field(gt=1)
    min_months: int = 1  # Phase 03: mismatch must persist N months
    lookback_days: int = Field(gt=0)
    min_income_floor: float = 0.0


class OffHoursCfg(BaseModel):
    night_start_hour_ist: int = Field(ge=0, le=23)
    night_end_hour_ist: int = Field(ge=0, le=23)
    sensitive_actions: list[str]


class SpikeCfg(BaseModel):
    lookback_days: int = Field(gt=0)
    personal_multiple: float = Field(gt=1)
    peer_multiple: float = Field(gt=1)
    min_day_count: int = Field(ge=1)


class HighRiskCfg(BaseModel):
    actions: list[str]


class BurstCfg(BaseModel):
    window_hours: int = Field(gt=0)
    min_actions: int = Field(ge=2)


class Thresholds(BaseModel):
    review_band: float = Field(gt=0)
    reporting_band: float = Field(gt=0)
    t1_circular: CircularCfg
    t2_structuring: StructuringCfg
    t3_fanin: FanInCfg
    t4_passthrough: PassthroughCfg
    t5_dormant: DormantCfg
    t6_profile: ProfileCfg
    e1_offhours: OffHoursCfg
    e3_spike: SpikeCfg
    e4_highrisk: HighRiskCfg
    e5_burst: BurstCfg


REQUIRED_BASE_POINTS = {"T1", "T2", "T3", "T4", "T5", "T6", "E1", "E2", "E3", "E4", "E5", "F1", "F2", "F3"}


class ScoringCfg(BaseModel):
    base_points: dict[str, int]
    modifiers: dict[str, int]
    params: dict[str, int] = {}  # modifier thresholds (e.g. amount_gt_5l_threshold)
    bands: dict[str, int]

    @field_validator("base_points")
    @classmethod
    def _all_rules_present(cls, v: dict[str, int]) -> dict[str, int]:
        missing = REQUIRED_BASE_POINTS - set(v)
        extra = set(v) - REQUIRED_BASE_POINTS
        if missing:
            raise ValueError(f"scoring.base_points missing rules: {sorted(missing)}")
        if extra:
            raise ValueError(f"scoring.base_points has unknown rules: {sorted(extra)}")
        return v


class FusionCfg(BaseModel):
    window_hours: int = Field(gt=0)
    f1_txn_rules: list[str] = ["T1", "T2", "T3", "T5"]
    max_rules_per_alert: int = Field(ge=2)
    max_entities_per_alert: int = Field(ge=4)


class GuardsCfg(BaseModel):
    exempt_purposes: list[str]


class RulesConfig(BaseModel):
    thresholds: Thresholds
    scoring: ScoringCfg
    fusion: FusionCfg
    legitimacy_guards: GuardsCfg


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise RulesConfigError(f"rules.yaml not found at {path} (set RULES_CONFIG env or fix the path)")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RulesConfigError(f"rules.yaml at {path} is empty or not a mapping")
    return data


@lru_cache
def get_rules_config(path_str: str) -> RulesConfig:
    """Cached, typed, validated. Raises RulesConfigError naming the missing key."""
    path = Path(path_str)
    raw = _load_yaml(path)
    try:
        return RulesConfig.model_validate(raw)
    except ValidationError as e:
        missing = [f"{'.'.join(str(p) for p in err['loc'])}" for err in e.errors()]
        raise RulesConfigError(f"rules.yaml invalid ({path}) — offending keys: {', '.join(missing)}") from e
