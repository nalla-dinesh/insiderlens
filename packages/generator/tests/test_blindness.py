"""Blindness law: nothing in the operational CSVs may reveal scenario membership.
This is what keeps Phase 04 evaluation honest and Phase 07 demo credible.
"""

from __future__ import annotations

import json
import re

from generator.verify import CSV_FILES

GT_TOKENS = re.compile(r"\b(S[1-7]|L[1-5])\b")
GT_COLUMNS = {"scenario_id", "is_suspicious", "gt_id"}
OPERATIONAL = [n for n in CSV_FILES if n != "ground_truth"]


def test_no_gt_columns_in_operational_frames(built):
    for name in OPERATIONAL:
        assert not (set(built[name].columns) & GT_COLUMNS), f"{name} leaks GT columns"


def test_no_scenario_tokens_in_any_operational_value(built):
    for name in OPERATIONAL:
        df = built[name]
        for col in df.columns:
            vals = df[col]
            if vals.dtype == object:
                for v in vals.dropna().astype(str):
                    assert not GT_TOKENS.search(v), f"{name}.{col} contains a scenario token: {v!r}"


def test_details_json_has_no_gt_vocabulary(built):
    for raw in built["activity_log"]["details"].astype(str):
        d = json.loads(raw)
        assert not (set(d.keys()) & GT_COLUMNS)
        for v in d.values():
            assert not GT_TOKENS.search(str(v))


def test_ground_truth_stays_separate_file(built):
    out = built["_out_dir"]
    names = sorted(p.stem for p in out.glob("*.csv"))
    assert "ground_truth" in names
    assert names == sorted(CSV_FILES)
