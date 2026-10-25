"""rules.yaml -> RulesConfig: valid file yields typed values; a missing key
mentions itself by name in the startup error (fail-fast law)."""

import pytest

from app.services.rules_config import RulesConfigError, get_rules_config
from tests.conftest import RULES_YAML


def test_real_rules_yaml_loads_typed():
    cfg = get_rules_config(str(RULES_YAML))
    assert cfg.thresholds.review_band == 50_000
    assert cfg.thresholds.reporting_band == 1_000_000
    assert cfg.thresholds.t1_circular.min_retention == 0.70
    assert cfg.thresholds.t4_passthrough.min_occurrences == 5
    assert cfg.thresholds.t4_passthrough.max_fraction_std == 0.10
    assert cfg.thresholds.t4_passthrough.min_route_share == 0.5
    assert cfg.thresholds.t3_fanin.leg_min_amount == 40_000
    assert cfg.thresholds.t6_profile.multiple == 25
    assert cfg.thresholds.t6_profile.min_months == 2
    assert cfg.thresholds.t5_dormant.dormant_days == 180
    assert cfg.scoring.bands == {"MEDIUM": 40, "HIGH": 70, "CRITICAL": 90}
    assert set(cfg.scoring.base_points) == {
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "F1",
        "F2",
        "F3",
    }
    assert "SALARY" in cfg.legitimacy_guards.exempt_purposes
    assert cfg.fusion.window_hours == 72


def test_missing_key_names_itself(tmp_path):
    broken = tmp_path / "rules.yaml"
    broken.write_text(
        "thresholds:\n  review_band: 50000\n  reporting_band: 1000000\n"
        "scoring:\n  base_points: {T1: 40}\n  modifiers: {}\n  bands: {MEDIUM: 40}\n"
        "fusion:\n  window_hours: 72\n"
        "legitimacy_guards:\n  exempt_purposes: []\n",
        encoding="utf-8",
    )
    with pytest.raises(RulesConfigError) as err:
        get_rules_config(str(broken))
    msg = str(err.value)
    assert "t1_circular" in msg and "t4_passthrough" in msg


def test_scoring_base_points_must_cover_all_14_rules(tmp_path):
    full = {
        "thresholds": {
            "review_band": 50000,
            "reporting_band": 1000000,
            "t1_circular": {"window_days": 10, "min_retention": 0.7, "min_len": 3, "max_len": 6},
            "t2_structuring": {"band_lo": 45000, "band_hi": 49999, "min_count": 5, "window_days": 7},
            "t3_fanin": {
                "min_in_degree": 8,
                "window_days": 5,
                "sub_threshold_fraction": 0.8,
                "bulk_out_multiple": 5,
                "bulk_window_hours": 48,
            },
            "t4_passthrough": {
                "forward_ratio": 0.8,
                "window_hours": 48,
                "min_occurrences": 3,
                "max_kept_fraction": 0.12,
            },
            "t5_dormant": {"dormant_days": 180, "burst_amount": 50000, "burst_window_hours": 72},
            "t6_profile": {"multiple": 6, "lookback_days": 30},
            "e1_offhours": {
                "night_start_hour_ist": 22,
                "night_end_hour_ist": 6,
                "sensitive_actions": ["KYC_EDIT"],
            },
            "e3_spike": {
                "lookback_days": 30,
                "personal_multiple": 3.0,
                "peer_multiple": 3.0,
                "min_day_count": 5,
            },
            "e4_highrisk": {"actions": ["DISABLE_ALERT", "LIMIT_INCREASE", "KYC_EDIT"]},
            "e5_burst": {"window_hours": 24, "min_actions": 4},
        },
        "scoring": {
            "base_points": {"T1": 40},  # 13 rules missing
            "modifiers": {"cross_branch": 10},
            "bands": {"MEDIUM": 40},
        },
        "fusion": {"window_hours": 72, "max_rules_per_alert": 6, "max_entities_per_alert": 20},
        "legitimacy_guards": {"exempt_purposes": []},
    }
    p = tmp_path / "rules.yaml"
    import yaml as _yaml

    p.write_text(_yaml.safe_dump(full), encoding="utf-8")
    with pytest.raises(RulesConfigError) as err:
        get_rules_config(str(p))
    assert "base_points" in str(err.value)


def test_missing_file_is_clear(tmp_path):
    with pytest.raises(RulesConfigError) as err:
        get_rules_config(str(tmp_path / "nope.yaml"))
    assert "not found" in str(err.value)


def test_cache_returns_same_object():
    a = get_rules_config(str(RULES_YAML))
    b = get_rules_config(str(RULES_YAML))
    assert a is b
